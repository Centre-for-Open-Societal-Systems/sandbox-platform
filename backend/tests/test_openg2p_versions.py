"""OpenG2P versions: PM 1.0 (COSS today: a key is needed to onboard, keys are copied,
no policies) vs develop (live JWKS, policies); data policies filed in the COSS Consent
Manager (bindings, AWE approves widenings) or in PM; the contract module."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import settings
from app.core.exceptions import UpstreamError
from app.integrations import consent_manager_admin as cm
from app.integrations import openg2p_contract
from app.integrations import partner_management as pm
from app.models.app import ParticipantPmPolicy
from app.models.participant import Participant
from app.schemas.app import PmPolicy
from app.services import partner_portal_service, pm_policy_service
from app.services.partner_portal_service import public_jwk
from tests import test_apps
from tests.test_iam_users import _decide, _login, _signup
from tests.test_partner_portal import FakePM, PortalKeycloak, _row
from tests.test_pm_policies import FARMER, LOAN, _product, _set_policy

farmer_endpoints = test_apps.farmer_endpoints  # fixture


def _pem():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key() \
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


# --------------------------------------------------------------- contract
def test_product_policy_fields_are_the_contracts():
    assert tuple(PmPolicy.model_fields) == openg2p_contract.PM_POLICY_FIELDS


def test_profiles_say_what_each_pm_release_offers():
    old, new = openg2p_contract.PM_PROFILES["1.0"], openg2p_contract.PM_PROFILES["develop"]
    assert not (old.live_jwks or old.policies or old.use_cases or old.catalogue)
    assert new.live_jwks and new.policies and new.use_cases and new.catalogue
    assert "keys_from_jwks_url" not in openg2p_contract.PM_ONBOARDING_FIELDS["1.0"]


# ------------------------------------------------------- PM release detection
def _calls(monkeypatch, answers):
    sent = []

    def fake_call(method, path, json=None, params=None, missing_ok=False):
        sent.append((method, path, json))
        return answers.get(path)

    monkeypatch.setattr(pm, "_call", fake_call)
    return sent


def test_auto_detects_the_pm_release(monkeypatch):
    monkeypatch.setattr(settings, "PM_STAFF_API_URL", "http://pm-detect-1.internal")
    sent = _calls(monkeypatch, {})  # GET /metadata -> 404 (None)
    assert pm.profile().name == "1.0"
    assert pm.profile().name == "1.0" and len(sent) == 1  # cached
    monkeypatch.setattr(settings, "PM_STAFF_API_URL", "http://pm-detect-2.internal")
    _calls(monkeypatch, {"/metadata": {"algorithms": []}})
    assert pm.profile().name == "develop"
    monkeypatch.setattr(settings, "PM_API_VERSION", "1.0")
    assert pm.profile().name == "1.0"  # an explicit release wins


@pytest.mark.parametrize(("release", "expected"), [
    ("1.0", {"import_from_jwks_url": True}),
    ("develop", {"keys_from_jwks_url": True, "policies": [FARMER]}),
])
def test_onboarding_payload_follows_the_release(monkeypatch, release, expected):
    monkeypatch.setattr(settings, "PM_API_VERSION", release)
    monkeypatch.setattr(settings, "PM_PARTNER_JWKS_BASE_URL", "https://sandbox.example.org/oan")
    sent = _calls(monkeypatch, {"/partners/requests/onboarding": {"id": "r1"}})
    pm.onboard("PARTNER_OAN_P_1", "oan-p-1", "Agri", "Agri", "test", [FARMER])
    [(_, _, body)] = sent
    assert {k: body[k] for k in body if k not in ("partner_id", "name", "org_name", "description", "jwks_url")} \
        == expected
    assert set(body) <= set(openg2p_contract.PM_ONBOARDING_FIELDS[release])


# ------------------------------------------------------ PM 1.0 (COSS today)
class FakePM10(FakePM):
    """PM 1.0: onboarding copies keys; key updates; no policies."""

    def install(self, monkeypatch, policies="[]"):
        super().install(monkeypatch, policies)
        monkeypatch.setattr(settings, "PM_API_VERSION", "1.0")
        self.kids: dict[str, set[str]] = {}
        self.key_updates: list[dict] = []
        monkeypatch.setattr(pm, "active_kids", lambda pm_id: set(self.kids.get(pm_id, set())))
        monkeypatch.setattr(pm, "open_request", lambda pm_id, kind: None)
        monkeypatch.setattr(pm, "key_update", self.key_update)
        return self

    def onboard(self, pm_id, partner_id, name, org_name, description, policies):
        request = super().onboard(pm_id, partner_id, name, org_name, description, policies)
        self.kids[pm_id] = {self.current_kid}
        return request

    def key_update(self, pm_id, partner_id, description, revoke_kids):
        self.key_updates.append({"pm_id": pm_id, "revoke": revoke_kids})
        self.kids[pm_id] = (self.kids[pm_id] - set(revoke_kids)) | {self.current_kid}
        request_id = f"ku-{len(self.key_updates)}"
        self.requests[request_id] = {"id": request_id, "partner_id": pm_id, "status": "created"}
        return self.requests[request_id]


def test_pm_10_waits_for_the_key_then_copies_it_and_follows_key_changes(
    client, db_session, admin_headers, monkeypatch
):
    PortalKeycloak().install(monkeypatch)
    fake = FakePM10().install(monkeypatch)
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)
    assert _row(db_session).pm_status == "NO_KEY" and "onboard" not in fake.calls  # PM 1.0 needs a key

    participant = db_session.get(Participant, user.participant_id)
    participant.public_key = _pem()
    db_session.commit()
    fake.current_kid = public_jwk(participant.public_key)["kid"]
    partner_portal_service.refresh_pending(db_session)
    assert _row(db_session).pm_status == "ACTIVE" and fake.calls.count("onboard") == 1

    old_kid = fake.current_kid
    participant.public_key = _pem()  # the partner registers a new key
    db_session.commit()
    fake.current_kid = public_jwk(participant.public_key)["kid"]
    from app.services import iam_user_service

    iam_user_service.sync(db_session, participant)
    assert fake.key_updates == [{"pm_id": f"PARTNER_OAN_P_{user.participant_id}", "revoke": [old_kid]}]


# ------------------------------------------------------ COSS Consent Manager
class FakeCM:
    """The CM staff API: bindings and policy versions; AWE decides widenings."""

    def __init__(self, awe=True):
        self.bindings: dict[str, dict] = {}
        self.versions: dict[str, list[dict]] = {}
        self.awe = awe

    def install(self, monkeypatch):
        for name, value in {"CM_ADMIN_API_URL": "http://cm-api.internal",
                            "CM_ADMIN_TOKEN_URL": "http://kc/realms/staff/protocol/openid-connect/token",
                            "CM_ADMIN_CLIENT_SECRET": "cm-secret"}.items():
            monkeypatch.setattr(settings, name, value)
        for name in ("find_binding", "create_binding", "set_binding_status", "upsert_policy", "list_policies", "meta"):
            monkeypatch.setattr(cm, name, getattr(self, name))
        return self

    def find_binding(self, audience, controller_id):
        return next((b for b in self.bindings.values()
                     if b["audience"] == audience and b["controller_id"] == controller_id), None)

    def create_binding(self, audience, controller_id, partner_mgmt_id, name):
        binding_id = f"b{len(self.bindings) + 1}"
        self.bindings[binding_id] = {"id": binding_id, "audience": audience, "controller_id": controller_id,
                                     "partner_mgmt_id": partner_mgmt_id, "status": "active"}
        return self.bindings[binding_id]

    def set_binding_status(self, binding_id, status):
        self.bindings[binding_id]["status"] = status
        return self.bindings[binding_id]

    def upsert_policy(self, binding_id, fields):
        versions = self.versions.setdefault(binding_id, [])
        if any(v["status"] == "pending" for v in versions):
            raise cm.PolicyPending(next(v["version"] for v in versions if v["status"] == "pending"))
        widening = not versions or set(fields.get("allowed_data_scopes", [])) - set(
            next((v["fields"].get("allowed_data_scopes", []) for v in reversed(versions)
                  if v["status"] == "active"), []))
        status = "pending" if (self.awe and widening) else "active"
        versions.append({"version": len(versions) + 1, "status": status, "fields": fields})
        return versions[-1]

    def list_policies(self, binding_id):
        return self.versions.get(binding_id, [])

    def meta(self):
        return {"known_controller_ids": ["farmer_registry"], "known_data_scopes": ["farmer_personal_details"]}

    def awe_decides(self, approve=True):
        for versions in self.versions.values():
            for v in versions:
                if v["status"] == "pending":
                    v["status"] = "active" if approve else "rejected"


@pytest.fixture
def coss(monkeypatch):
    """COSS today: PM 1.0 (keys only) + policies in the Consent Manager."""
    PortalKeycloak().install(monkeypatch)
    test_apps.FakeGateway(test_apps._routes()).install(monkeypatch)
    fake_pm = FakePM10().install(monkeypatch)
    return fake_pm, FakeCM().install(monkeypatch)


def _coss_partner(client, db_session, admin_headers, fake_pm):
    user = _signup(client, db_session)
    participant = db_session.get(Participant, user.participant_id)
    participant.public_key = _pem()
    db_session.commit()
    fake_pm.current_kid = public_jwk(participant.public_key)["kid"]
    _decide(client, admin_headers, user)
    return user, _login(client)


def _cm_rows(db_session):
    db_session.expire_all()
    return {r.policy_key: r for r in db_session.query(ParticipantPmPolicy).filter_by(backend="cm")}


def test_auto_backend_is_the_consent_manager_while_pm_has_no_policies(coss):
    backend = pm_policy_service.backend_for("UAT")
    assert (backend.kind, backend.environment) == ("cm", "UAT")


def test_policy_becomes_a_cm_binding_that_awe_approves(client, db_session, admin_headers, farmer_endpoints, coss):
    fake_pm, fake_cm = coss
    user, headers = _coss_partner(client, db_session, admin_headers, fake_pm)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)

    test_apps._create_app(client, headers, "Server App", [read], admin_headers)

    [binding] = fake_cm.bindings.values()
    assert binding == {"id": "b1", "audience": f"oan-p-{user.participant_id}", "controller_id": "farmer_registry",
                       "partner_mgmt_id": f"PARTNER_OAN_P_{user.participant_id}", "status": "active"}
    [version] = fake_cm.versions["b1"]
    assert version["fields"] == {"allowed_data_scopes": ["farmer_personal_details"],
                                 "allowed_signing_algs": ["RS256"], "consent_method": "otp"}
    row = _cm_rows(db_session)["data_controller:farmer_registry"]
    assert (row.status, row.request_id) == ("PENDING", "b1#1")  # a widening: AWE decides

    fake_cm.awe_decides()
    pm_policy_service.refresh_pending(db_session)
    assert _cm_rows(db_session)["data_controller:farmer_registry"].status == "ACTIVE"

    _set_policy(client, admin_headers, read, None)  # no product asks for it any more
    assert fake_cm.bindings["b1"]["status"] == "suspended" and _cm_rows(db_session) == {}


def test_use_cases_are_not_sent_to_the_consent_manager(client, db_session, admin_headers, farmer_endpoints, coss):
    fake_pm, fake_cm = coss
    _, headers = _coss_partner(client, db_session, admin_headers, fake_pm)
    loan = _product(client, admin_headers, "loan-profile", farmer_endpoints[:1], LOAN)
    test_apps._create_app(client, headers, "Server App", [loan], admin_headers)
    row = _cm_rows(db_session)["use_case:loan-profile@1"]
    assert row.status == "REJECTED" and "no use-case policies" in row.error
    assert fake_cm.bindings == {}


def test_a_waiting_cm_version_is_followed_not_duplicated(client, db_session, admin_headers, farmer_endpoints, coss):
    fake_pm, fake_cm = coss
    _, headers = _coss_partner(client, db_session, admin_headers, fake_pm)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)
    test_apps._create_app(client, headers, "Server App", [read], admin_headers)
    _set_policy(client, admin_headers, read, {**FARMER, "allowed_data_scopes": ["farmer_personal_details", "x"]})
    assert len(fake_cm.versions["b1"]) == 1  # v1 still waits for AWE: nothing new filed
    fake_cm.awe_decides()
    pm_policy_service.refresh_pending(db_session)  # v1 approved
    pm_policy_service.refresh_pending(db_session)
    assert len(fake_cm.versions["b1"]) >= 1


def test_catalogue_from_the_consent_manager(client, admin_headers, coss):
    data = client.get("/oan/admin/api-products/pm-catalogue", headers=admin_headers).json()["data"]
    assert data["backend"] == "cm" and data["sources"][0]["data_controller"] == "farmer_registry"


def test_explicit_backends(monkeypatch, coss):
    monkeypatch.setattr(settings, "POLICY_BACKEND", "none")
    assert pm_policy_service.backends() == []
    monkeypatch.setattr(settings, "POLICY_BACKEND", "pm")
    assert pm_policy_service.backend_for("UAT") is None  # PM 1.0 has no policies
    monkeypatch.setattr(settings, "PM_API_VERSION", "develop")
    assert pm_policy_service.backend_for("UAT").kind == "pm"


def test_cm_unreachable_is_failed_and_retried(client, db_session, admin_headers, farmer_endpoints, coss, monkeypatch):
    fake_pm, fake_cm = coss
    _, headers = _coss_partner(client, db_session, admin_headers, fake_pm)
    real = cm.find_binding

    def down(*args):
        raise UpstreamError("The Consent Manager could not be reached at CM_ADMIN_API_URL.")

    monkeypatch.setattr(cm, "find_binding", down)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)
    test_apps._create_app(client, headers, "Server App", [read], admin_headers)
    assert _cm_rows(db_session)["data_controller:farmer_registry"].status == "FAILED"
    monkeypatch.setattr(cm, "find_binding", real)
    pm_policy_service.refresh_pending(db_session)
    assert _cm_rows(db_session)["data_controller:farmer_registry"].status == "PENDING"
    assert json.dumps(fake_cm.versions)
