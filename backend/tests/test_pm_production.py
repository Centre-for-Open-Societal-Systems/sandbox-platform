"""Production's own Partner Management (PM_PROD_*): a participant is onboarded there only
when production access is approved, with production's JWKS URL and policies; by default
the request waits for production PM's staff (maker-checker) and the sandbox reads the
outcome; taking production access away disables the partner there only."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import Settings, settings
from app.integrations import partner_management as pm
from app.models.participant import Participant
from app.services import iam_user_service, partner_portal_service
from tests.test_iam_users import _decide, _signup
from tests.test_partner_portal import FakePM, PortalKeycloak, _account, _row

UAT_POLICY = {"data_controller": "farmer_registry", "allowed_data_scopes": ["farmer_personal_details"]}
PROD_POLICY = {"use_case": "loan-profile@1"}


class FakePMs(FakePM):
    """One FakePM per PM (pm.current_target())."""

    def __init__(self):
        super().__init__()
        self.stores = {"UAT": ({}, {}), "PRODUCTION": ({}, {})}

    def install(self, monkeypatch, policies="[]"):
        super().install(monkeypatch, policies)
        for name, value in {
            "PM_PROD_STAFF_API_URL": "http://pm-staff.prod.internal",
            "PM_PROD_TOKEN_URL": "http://keycloak.prod.internal/realms/staff/protocol/openid-connect/token",
            "PM_PROD_CLIENT_SECRET": "pm-prod-secret",
            "PM_PROD_DEFAULT_POLICIES": json.dumps([PROD_POLICY]),
        }.items():
            monkeypatch.setattr(settings, name, value)
        for name in ("get_partner", "onboard", "open_onboarding_request", "approve", "disable", "enable"):
            monkeypatch.setattr(pm, name, self._per_pm(getattr(FakePM, name)))
        return self

    def _per_pm(self, method):
        """FakePM keeps partners / requests on self: point them at the current PM's."""
        def call(*args, **kwargs):
            self.partners, self.requests = self.stores[pm.current_target().environment]
            return method(self, *args, **kwargs)
        return call

    def store(self, env) -> dict:
        return self.stores[env][0]

    def staff_approves(self, env):
        """PM's own staff approve every open onboarding request."""
        partners, requests = self.stores[env]
        for request in requests.values():
            if request["status"] == "created":
                request["status"] = "approved"
                partners[request["partner_id"]]["status"] = "active"


@pytest.fixture
def pms(monkeypatch):
    PortalKeycloak().install(monkeypatch)
    return FakePMs().install(monkeypatch, policies=json.dumps([UAT_POLICY]))


def test_production_pm_gets_the_partner_only_with_production_access(client, db_session, admin_headers, pms):
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    pm_id = f"PARTNER_OAN_P_{user.participant_id}"
    assert pms.store("UAT")[pm_id]["status"] == "active"  # UAT PM: sandbox approves (PM_AUTO_APPROVE)
    assert pms.store("PRODUCTION") == {}
    assert _row(db_session).pm_prod_status is None

    _decide(client, admin_headers, user, environment="PRODUCTION")

    partner = pms.store("PRODUCTION")[pm_id]
    assert partner["status"] == "created"  # waits for production PM's staff
    assert partner["policies"] == [PROD_POLICY]
    assert partner["jwks_url"] == \
        f"https://api.sandbox.example.org/oan/partners/oan-p-{user.participant_id}/production/jwks.json"
    row = _row(db_session)
    assert (row.pm_status, row.pm_prod_status) == ("ACTIVE", "PENDING")
    portal = _account(client, admin_headers, user)["partner_portal"]
    assert (portal["pm_prod_enabled"], portal["pm_prod_status"]) == (True, "PENDING")

    pms.staff_approves("PRODUCTION")
    assert partner_portal_service.refresh_pending(db_session) == 1
    assert _row(db_session).pm_prod_status == "ACTIVE"
    assert partner_portal_service.refresh_pending(db_session) == 0


def test_losing_production_access_disables_only_the_production_partner(
    client, db_session, admin_headers, pms, monkeypatch
):
    monkeypatch.setattr(settings, "PM_PROD_AUTO_APPROVE", True)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    _decide(client, admin_headers, user, environment="PRODUCTION")
    pm_id = f"PARTNER_OAN_P_{user.participant_id}"
    assert pms.store("PRODUCTION")[pm_id]["status"] == "active"  # auto-approved when asked to

    participant = db_session.get(Participant, user.participant_id)
    participant.is_prod_enabled = False
    db_session.commit()
    iam_user_service.sync(db_session, participant)

    assert pms.store("PRODUCTION")[pm_id]["status"] == "disabled"
    assert pms.store("UAT")[pm_id]["status"] == "active"
    assert (_row(db_session).pm_status, _row(db_session).pm_prod_status) == ("ACTIVE", "DISABLED")


def test_uat_pm_can_also_wait_for_its_staff(client, db_session, admin_headers, pms, monkeypatch):
    monkeypatch.setattr(settings, "PM_AUTO_APPROVE", False)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    assert _row(db_session).pm_status == "PENDING"
    assert "approve" not in pms.calls

    pms.staff_approves("UAT")
    partner_portal_service.refresh_pending(db_session)
    assert _row(db_session).pm_status == "ACTIVE"


def test_production_jwks_only_with_production_access(client, db_session, admin_headers, pms):
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    participant = db_session.get(Participant, user.participant_id)
    participant.public_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key() \
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    db_session.commit()
    url = f"/oan/partners/oan-p-{user.participant_id}/production/jwks.json"
    assert client.get(url).status_code == 404  # UAT only

    _decide(client, admin_headers, user, environment="PRODUCTION")
    [key] = client.get(url).json()["keys"]
    assert key["kty"] == "RSA"


def test_no_production_pm_leaves_production_alone(client, db_session, admin_headers, pms, monkeypatch):
    monkeypatch.setattr(settings, "PM_PROD_STAFF_API_URL", "")
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    _decide(client, admin_headers, user, environment="PRODUCTION")
    assert pms.store("PRODUCTION") == {} and _row(db_session).pm_prod_status is None


@pytest.mark.parametrize(
    "values",
    [
        {"PM_PROD_STAFF_API_URL": "http://pm.prod"},  # no token URL / secret
        {"PM_DEFAULT_POLICIES": json.dumps([{"use_case": "loan-profile@1", "allowed_purposes": ["x"]}])},
        {"PM_PROD_DEFAULT_POLICIES": "{"},
    ],
)
def test_bad_pm_settings_are_refused(values):
    with pytest.raises(ValueError):
        Settings(**values)
