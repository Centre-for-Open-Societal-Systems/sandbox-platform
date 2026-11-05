"""Approved participants in the Consent Manager partner portal: Keycloak partner_id
attribute + portal role, and a partner in Partner Management (onboarded, approved,
disabled / enabled with the participant's access)."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

from app.config.settings import Settings, settings
from app.core.exceptions import UpstreamError
from app.integrations import keycloak
from app.integrations import partner_management as pm
from app.models.app import ParticipantIamUser
from app.models.participant import Participant
from tests.test_iam_users import SIGNUP, FakeKeycloak, _decide, _login, _signup

POLICY = {"data_controller": "farmer_registry", "allowed_data_scopes": ["farmer_personal_details"]}


class PortalKeycloak(FakeKeycloak):
    def install(self, monkeypatch):
        super().install(monkeypatch)
        monkeypatch.setattr(settings, "KEYCLOAK_REALM", "partner")
        monkeypatch.setattr(settings, "KEYCLOAK_PORTAL_CLIENT_ID", "consent-partner-portal")
        monkeypatch.setattr(keycloak, "set_portal_role", self.set_portal_role)
        return self

    def set_portal_role(self, user_id, granted):
        self._check()
        self.users[user_id]["portal"] = granted


class FakePM:
    """The PM staff API calls the sandbox makes, over an in-memory partner list."""

    def __init__(self):
        self.partners: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.calls: list[str] = []
        self.fail = False
        self.fail_approve = False

    def install(self, monkeypatch, policies="[]"):
        for name, value in {
            "PM_PROVISIONING_ENABLED": True,
            "PM_STAFF_API_URL": "http://pm-staff.internal",
            "PM_TOKEN_URL": "http://keycloak.internal:8080/realms/staff/protocol/openid-connect/token",
            "PM_CLIENT_SECRET": "pm-secret",
            "PM_PARTNER_JWKS_BASE_URL": "https://api.sandbox.example.org/oan",
            "PM_DEFAULT_POLICIES": policies,
        }.items():
            monkeypatch.setattr(settings, name, value)
        for name in ("get_partner", "onboard", "open_onboarding_request", "approve", "disable", "enable"):
            monkeypatch.setattr(pm, name, getattr(self, name))
        return self

    def _check(self, call):
        self.calls.append(call)
        if self.fail:
            raise UpstreamError("Partner Management could not be reached at PM_STAFF_API_URL.")

    def get_partner(self, pm_id):
        self._check("get")
        return self.partners.get(pm_id)

    def onboard(self, pm_id, partner_id, name, org_name, description, policies):
        self._check("onboard")
        self.partners[pm_id] = {"partner_id": pm_id, "name": name, "org_name": org_name,
                                "jwks_url": pm.jwks_url(partner_id), "policies": policies,
                                "status": "created"}
        request_id = f"req-{len(self.requests) + 1}"
        self.requests[request_id] = {"id": request_id, "partner_id": pm_id, "status": "created"}
        return self.requests[request_id]

    def open_onboarding_request(self, pm_id):
        self._check("open-request")
        return next((r for r in self.requests.values()
                     if r["partner_id"] == pm_id and r["status"] == "created"), None)

    def approve(self, request_id, notes):
        self._check("approve")
        if self.fail_approve:
            raise UpstreamError("Partner Management answered HTTP 500 for POST approve")
        request = self.requests[request_id]
        request["status"] = "approved"
        self.partners[request["partner_id"]]["status"] = "active"
        return request

    def disable(self, pm_id):
        self._check("disable")
        self.partners[pm_id]["status"] = "disabled"

    def enable(self, pm_id):
        self._check("enable")
        self.partners[pm_id]["status"] = "active"

    @property
    def only(self) -> dict:
        [partner] = self.partners.values()
        return partner


def _account(client, admin_headers, user) -> dict:
    response = client.get(f"/oan/admin/participants/{user.participant_id}/iam-account", headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["account"]


def _row(db_session) -> ParticipantIamUser:
    db_session.expire_all()
    return db_session.query(ParticipantIamUser).one()


def test_approval_gives_portal_access_and_a_pm_partner(client, db_session, admin_headers, monkeypatch):
    kc = PortalKeycloak().install(monkeypatch)
    fake_pm = FakePM().install(monkeypatch, policies=f"[{json.dumps(POLICY)}]")
    user = _signup(client, db_session)
    assert fake_pm.calls == []  # sign-up sends nothing anywhere

    _decide(client, admin_headers, user)

    partner_id = f"oan-p-{user.participant_id}"
    pm_id = f"PARTNER_OAN_P_{user.participant_id}"
    assert kc.only["attributes"] == {"participant_uid": str(user.unique_id), "partner_id": partner_id}
    assert kc.only["portal"] is True and kc.only["roles"] == {"uat"}
    assert fake_pm.only == {
        "partner_id": pm_id,
        "name": SIGNUP["company_name"],
        "org_name": SIGNUP["company_name"],
        "jwks_url": f"https://api.sandbox.example.org/oan/partners/{partner_id}/jwks.json",
        "policies": [POLICY],
        "status": "active",
    }
    row = _row(db_session)
    assert (row.partner_id, row.portal_access, row.pm_partner_id, row.pm_status) == (
        partner_id, True, pm_id, "ACTIVE")
    portal = _account(client, admin_headers, user)["partner_portal"]
    assert portal["partner_id"] == partner_id and portal["client_id"] == "consent-partner-portal"
    assert (portal["role"], portal["portal_access"]) == ("PARTNER_OPERATOR", True)
    assert (portal["pm_partner_id"], portal["pm_status"], portal["pm_error"]) == (pm_id, "ACTIVE", None)

    # Production approval later: same partner, nothing new in PM.
    _decide(client, admin_headers, user, environment="PRODUCTION")
    assert len(fake_pm.partners) == 1 and fake_pm.calls.count("onboard") == 1


def test_reject_disables_and_approve_enables_again(client, db_session, admin_headers, monkeypatch):
    kc = PortalKeycloak().install(monkeypatch)
    fake_pm = FakePM().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    _decide(client, admin_headers, user, action="reject")
    assert kc.only["portal"] is False and kc.only["enabled"] is False
    assert fake_pm.only["status"] == "disabled"
    assert (_row(db_session).portal_access, _row(db_session).pm_status) == (False, "DISABLED")

    _decide(client, admin_headers, user)
    assert kc.only["portal"] is True and fake_pm.only["status"] == "active"
    assert _row(db_session).pm_status == "ACTIVE"
    assert fake_pm.calls.count("onboard") == 1


def test_disable_and_delete_disable_the_pm_partner(client, db_session, admin_headers, monkeypatch):
    PortalKeycloak().install(monkeypatch)
    fake_pm = FakePM().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    toggled = client.post(
        "/oan/admin/participants/toggle", headers=admin_headers,
        json={"id": user.participant_id, "is_enabled": False},
    )
    assert toggled.status_code == 200, toggled.text
    assert fake_pm.only["status"] == "disabled"

    deleted = client.delete(f"/oan/admin/participants/{user.participant_id}", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    assert fake_pm.only["status"] == "disabled" and _row(db_session).pm_status == "DISABLED"


def test_pm_failure_keeps_keycloak_and_can_be_retried(client, db_session, admin_headers, monkeypatch):
    kc = PortalKeycloak().install(monkeypatch)
    fake_pm = FakePM().install(monkeypatch)
    fake_pm.fail = True
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    row = _row(db_session)
    assert (row.status, row.portal_access) == ("ACTIVE", True) and kc.only["portal"] is True
    assert row.pm_status == "FAILED" and "could not be reached" in row.pm_error

    fake_pm.fail = False
    retried = client.post(
        f"/oan/admin/participants/{user.participant_id}/iam-account/retry", headers=admin_headers
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["data"]["account"]["partner_portal"]["pm_status"] == "ACTIVE"
    assert fake_pm.only["status"] == "active"


def test_an_unapproved_onboarding_is_approved_on_retry(client, db_session, admin_headers, monkeypatch):
    PortalKeycloak().install(monkeypatch)
    fake_pm = FakePM().install(monkeypatch)
    fake_pm.fail_approve = True
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    assert fake_pm.only["status"] == "created" and _row(db_session).pm_status == "FAILED"

    fake_pm.fail_approve = False
    client.post(f"/oan/admin/participants/{user.participant_id}/iam-account/retry", headers=admin_headers)
    assert fake_pm.only["status"] == "active" and _row(db_session).pm_status == "ACTIVE"
    assert fake_pm.calls.count("onboard") == 1


def test_sign_in_does_not_wait_for_pm(client, db_session, admin_headers, monkeypatch):
    kc = PortalKeycloak().install(monkeypatch)
    fake_pm = FakePM().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    before = list(fake_pm.calls)

    fake_pm.fail = True  # PM down: the portal sign-in is not affected
    _login(client)
    assert kc.only["password"] == SIGNUP["password"]
    assert fake_pm.calls == before and _row(db_session).pm_status == "ACTIVE"


def test_portal_without_pm_still_sets_keycloak(client, db_session, admin_headers, monkeypatch):
    kc = PortalKeycloak().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)

    assert kc.only["attributes"]["partner_id"] == f"oan-p-{user.participant_id}"
    assert kc.only["portal"] is True
    row = _row(db_session)
    assert (row.pm_partner_id, row.pm_status) == (None, None)
    assert _account(client, admin_headers, user)["partner_portal"]["pm_enabled"] is False


def test_partner_jwks(client, db_session, admin_headers, monkeypatch):
    PortalKeycloak().install(monkeypatch)
    user = _signup(client, db_session)
    url = f"/oan/partners/oan-p-{user.participant_id}/jwks.json"
    assert client.get(url).status_code == 404  # not approved yet

    _decide(client, admin_headers, user)
    assert client.get(url).json() == {"keys": []}  # no key given yet
    assert client.get("/oan/partners/oan-p-999999/jwks.json").status_code == 404

    participant = db_session.get(Participant, user.participant_id)
    participant.public_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key() \
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    db_session.commit()
    [key] = client.get(url).json()["keys"]
    assert (key["kty"], key["alg"], key["use"]) == ("RSA", "RS256", "sig") and key["kid"] and key["n"]

    participant.public_key = ed25519.Ed25519PrivateKey.generate().public_key() \
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    db_session.commit()
    [key] = client.get(url).json()["keys"]
    assert (key["kty"], key["crv"], key["alg"]) == ("OKP", "Ed25519", "EdDSA")

    participant.public_key = "-----BEGIN PUBLIC KEY-----abc-----END PUBLIC KEY-----"
    db_session.commit()
    assert client.get(url).json() == {"keys": []}

    _decide(client, admin_headers, user, action="reject")
    assert client.get(url).status_code == 404


def test_pm_partner_id_convention():
    assert pm.pm_partner_id("oan-p-42") == "PARTNER_OAN_P_42"


@pytest.mark.parametrize("value", ["{", '{"a": 1}', "[1]"])
def test_default_policies_must_be_a_json_list_of_objects(value):
    with pytest.raises(ValueError):
        Settings(PM_DEFAULT_POLICIES=value)
