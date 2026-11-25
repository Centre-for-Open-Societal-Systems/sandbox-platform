"""D3: API products ask for OpenG2P Partner Management policies. Approving such a product
for an app files a *policy request* in the app's environment's PM; PM's staff decide
(the UAT PM may auto-approve). Nothing is filed while the PM partner is not active;
products asking for the same key are merged; a policy no product asks for any more is
revoked; a rejected policy is filed again only when the products ask for something else."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.config.settings import settings
from app.integrations import partner_management as pm
from app.models.app import ParticipantPmPolicy
from app.models.participant import Participant
from app.schemas.app import PmPolicy
from app.services import partner_portal_service, pm_policy_service
from tests import test_apps
from tests.test_apps import FakeGateway, _create_app, _routes
from tests.test_iam_users import _decide, _login, _signup
from tests.test_partner_portal import PortalKeycloak, _account
from tests.test_pm_production import FakePMs
from tests.test_production_environment import production_app

farmer_endpoints = test_apps.farmer_endpoints  # fixture

FARMER = {"data_controller": "farmer_registry", "allowed_data_scopes": ["farmer_personal_details"]}
LOAN = {"use_case": "loan-profile@1"}


class PolicyPMs(FakePMs):
    """FakePMs plus policy requests, their outcome and the catalogue."""

    def install(self, monkeypatch, policies="[]"):
        super().install(monkeypatch, policies)
        self.active: dict[str, dict[str, dict]] = {"UAT": {}, "PRODUCTION": {}}
        for name in ("request_policies", "get_request", "catalogue"):
            monkeypatch.setattr(pm, name, getattr(self, name))
        monkeypatch.setattr(pm, "approve", self.approve_any)
        return self

    @staticmethod
    def env() -> str:
        return pm.current_target().environment

    def request_policies(self, pm_id, description, policies, revoke):
        self.calls.append("policy-request")
        partners, requests = self.stores[self.env()]
        assert partners[pm_id]["status"] == "active", "PM takes policy requests for active partners only"
        request_id = f"{self.env()}-req-{len(requests) + 1}"
        requests[request_id] = {"id": request_id, "partner_id": pm_id, "status": "created", "type": "policy",
                                "policies": policies, "revoke": revoke, "description": description}
        return requests[request_id]

    def get_request(self, request_id):
        return self.stores[self.env()][1].get(request_id)

    def catalogue(self):
        return [{"kind": "scopes", "data_controller": "farmer_registry", "label": "Farmer registry",
                 "items": [{"id": "farmer_personal_details"}]}]

    def approve_any(self, request_id, notes):
        partners, requests = self.stores[self.env()]
        self._apply(partners, requests[request_id])
        return requests[request_id]

    def decide(self, env, approve=True, notes=None):
        """PM's own staff decide every open request."""
        partners, requests = self.stores[env]
        for request in requests.values():
            if request["status"] == "created":
                if approve:
                    self._apply(partners, request)
                else:
                    request["status"], request["review_notes"] = "rejected", notes

    def _apply(self, partners, request):
        request["status"] = "approved"
        if request.get("type") != "policy":
            partners[request["partner_id"]]["status"] = "active"
            return
        env = next(e for e, (p, _) in self.stores.items() if p is partners)
        for policy in request["policies"]:
            self.active[env][pm_policy_service.policy_key(policy)] = policy
        for ref in request["revoke"]:
            self.active[env].pop(pm_policy_service.policy_key(ref), None)

    def policy_requests(self, env) -> list[dict]:
        return [r for r in self.stores[env][1].values() if r.get("type") == "policy"]


@pytest.fixture
def pms(monkeypatch):
    PortalKeycloak().install(monkeypatch)
    FakeGateway(_routes()).install(monkeypatch)
    return PolicyPMs().install(monkeypatch)


def _product(client, admin_headers, name, endpoint_ids, policy=None, approval="AUTO") -> int:
    body = {"name": name, "display_name": name.replace("-", " ").title(), "approval_type": approval,
            "is_published": True, "endpoint_ids": endpoint_ids}
    if policy is not None:
        body["pm_policy"] = policy
    response = client.post("/oan/admin/api-products", headers=admin_headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()["data"]["api_product_id"]


def _set_policy(client, admin_headers, product_id, policy):
    detail = client.get(f"/oan/admin/api-products/{product_id}", headers=admin_headers).json()["data"]
    body = {k: detail[k] for k in ("name", "display_name", "description", "approval_type", "is_published",
                                   "sort_order", "rate_limit_per_minute", "quota_per_day")}
    body["endpoint_ids"] = [e["endpoint_id"] for e in detail["endpoints"]]
    body["pm_policy"] = policy
    response = client.put(f"/oan/admin/api-products/{product_id}", headers=admin_headers, json=body)
    assert response.status_code == 200, response.text


def _partner(client, db_session, admin_headers) -> tuple[Participant, dict]:
    user = _signup(client, db_session)
    _decide(client, admin_headers, user)  # UAT: PM partner onboarded and (auto-)approved
    return user, _login(client)


def _rows(db_session, env="UAT") -> dict[str, ParticipantPmPolicy]:
    db_session.expire_all()
    return {r.policy_key: r for r in db_session.query(ParticipantPmPolicy).filter_by(environment=env)}


def test_approved_product_files_its_policy_in_the_uat_pm(client, db_session, admin_headers, farmer_endpoints, pms):
    user, headers = _partner(client, db_session, admin_headers)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)

    _create_app(client, headers, "Server App", [read], admin_headers)

    [request] = pms.policy_requests("UAT")
    assert request["status"] == "approved"  # UAT PM: PM_AUTO_APPROVE
    assert request["policies"] == [FARMER]  # no key registered: PM's default algorithms
    assert "API products: Farmer Read" in request["description"]
    assert pms.active["UAT"] == {"data_controller:farmer_registry": FARMER}
    row = _rows(db_session)["data_controller:farmer_registry"]
    assert (row.status, row.products) == ("ACTIVE", ["Farmer Read"])

    seen = client.get("/oan/participant/data-access", headers=headers).json()["data"]["policies"]
    assert [(p["policy_key"], p["status"]) for p in seen] == [("data_controller:farmer_registry", "ACTIVE")]
    console = _account(client, admin_headers, user)["partner_portal"]["pm_policies"]
    assert console[0]["request_id"] == request["id"]


def test_products_asking_for_the_same_key_are_merged_and_dropped_ones_revoked(
    client, db_session, admin_headers, farmer_endpoints, pms
):
    _, headers = _partner(client, db_session, admin_headers)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)
    more = _product(client, admin_headers, "farmer-more", farmer_endpoints[2:3],
                    {**FARMER, "allowed_data_scopes": ["farmer_land_details"], "allow_partner_consents": True})
    _create_app(client, headers, "Server App", [read, more], admin_headers)

    merged = pms.active["UAT"]["data_controller:farmer_registry"]
    assert merged["allowed_data_scopes"] == ["farmer_personal_details", "farmer_land_details"]
    assert merged["allow_partner_consents"] is True
    assert _rows(db_session)["data_controller:farmer_registry"].products == ["Farmer Read", "Farmer More"]

    _set_policy(client, admin_headers, read, None)
    _set_policy(client, admin_headers, more, None)
    assert pms.active["UAT"] == {}
    assert _rows(db_session) == {}
    assert pms.policy_requests("UAT")[-1]["revoke"] == [{"data_controller": "farmer_registry"}]


def test_production_policies_wait_for_the_partner_and_for_pm_staff(
    client, db_session, admin_headers, farmer_endpoints, pms
):
    user, headers = _partner(client, db_session, admin_headers)
    loan = _product(client, admin_headers, "loan-profile", farmer_endpoints[:1], LOAN)
    uat = _create_app(client, headers, "Server App", [loan], admin_headers)
    participant = db_session.get(Participant, user.participant_id)
    participant.public_key = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key() \
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    db_session.commit()
    _decide(client, admin_headers, user, environment="PRODUCTION")  # production PM: onboarding waits for staff

    production_app(client, admin_headers, headers, uat["app"]["app_id"])

    row = _rows(db_session, "PRODUCTION")["use_case:loan-profile@1"]
    assert row.status == "WAITING" and pms.policy_requests("PRODUCTION") == []  # partner not active there yet

    pms.staff_approves("PRODUCTION")  # production PM's staff approve the onboarding
    partner_portal_service.refresh_pending(db_session)
    pm_policy_service.refresh_pending(db_session)
    [request] = pms.policy_requests("PRODUCTION")
    assert request["status"] == "created"  # filed, never approved by the sandbox in production
    assert request["policies"] == [{**LOAN, "allowed_signing_algs": ["RS256"]}]  # the partner's key
    assert _rows(db_session, "PRODUCTION")["use_case:loan-profile@1"].status == "PENDING"

    pms.decide("PRODUCTION", approve=False, notes="Use case not offered to this partner type.")
    pm_policy_service.refresh_pending(db_session)
    row = _rows(db_session, "PRODUCTION")["use_case:loan-profile@1"]
    assert (row.status, row.error) == ("REJECTED", "Use case not offered to this partner type.")
    pm_policy_service.sync_participant(db_session, user.participant_id)
    assert len(pms.policy_requests("PRODUCTION")) == 1  # not filed again as it is

    _set_policy(client, admin_headers, loan, {**LOAN, "allow_partner_consents": True})  # asks for something else
    assert len(pms.policy_requests("PRODUCTION")) == 2
    pms.decide("PRODUCTION")
    pm_policy_service.refresh_pending(db_session)
    assert _rows(db_session, "PRODUCTION")["use_case:loan-profile@1"].status == "ACTIVE"
    assert "use_case:loan-profile@1" in pms.active["PRODUCTION"]


def test_a_pm_failure_is_kept_and_retried(client, db_session, admin_headers, farmer_endpoints, pms, monkeypatch):
    _, headers = _partner(client, db_session, admin_headers)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)
    real = pms.request_policies

    def down(*args, **kwargs):
        raise pm.UpstreamError("Partner Management could not be reached at PM_STAFF_API_URL.")

    monkeypatch.setattr(pm, "request_policies", down)
    created = _create_app(client, headers, "Server App", [read], admin_headers)
    assert created["app"]["status_label"]  # the app itself is approved regardless
    row = _rows(db_session)["data_controller:farmer_registry"]
    assert row.status == "FAILED" and "could not be reached" in row.error

    monkeypatch.setattr(pm, "request_policies", real)
    pm_policy_service.refresh_pending(db_session)
    assert _rows(db_session)["data_controller:farmer_registry"].status == "ACTIVE"


def test_without_pm_nothing_is_filed(client, db_session, admin_headers, farmer_endpoints, pms, monkeypatch):
    monkeypatch.setattr(settings, "PM_PROVISIONING_ENABLED", False)
    _, headers = _partner(client, db_session, admin_headers)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], FARMER)
    _create_app(client, headers, "Server App", [read], admin_headers)
    assert pms.policy_requests("UAT") == [] and _rows(db_session) == {}


def test_catalogue_for_the_product_form(client, admin_headers, pms):
    data = client.get("/oan/admin/api-products/pm-catalogue", headers=admin_headers).json()["data"]
    assert data["enabled"] is True and data["sources"][0]["data_controller"] == "farmer_registry"


@pytest.mark.parametrize(
    "policy",
    [
        {"data_controller": "farmer_registry"},  # no scopes
        {"use_case": "loan-profile"},  # no @major
        {"use_case": "loan-profile@1", "allowed_purposes": ["x"]},  # purposes on a use case
        {"use_case": "loan-profile@1", "allowed_data_scopes": ["x"]},
        {"data_controller": "farmer_registry", "use_case": "loan-profile@1", "allowed_data_scopes": ["x"]},
        {**FARMER, "allowed_signing_algs": ["HS256"]},
        {**FARMER, "data_life": "30 days"},
        {**FARMER, "unknown": True},
    ],
)
def test_invalid_policies_are_refused(policy, client, admin_headers, farmer_endpoints):
    with pytest.raises(ValidationError):
        PmPolicy(**policy)
    response = client.post("/oan/admin/api-products", headers=admin_headers, json={
        "name": "bad-policy", "display_name": "Bad", "endpoint_ids": farmer_endpoints[:1], "pm_policy": policy})
    assert response.status_code in (400, 422)


def test_policy_is_stored_without_empty_fields(client, admin_headers, farmer_endpoints):
    product = _product(client, admin_headers, "farmer-read", farmer_endpoints[:1],
                       {**FARMER, "allowed_purposes": [" ", "p1", "p1"], "data_life": "p30d", "fetch_type": "oneshot"})
    detail = client.get(f"/oan/admin/api-products/{product}", headers=admin_headers).json()["data"]
    assert detail["pm_policy"] == {**FARMER, "allowed_purposes": ["p1"], "data_life": "P30D"}
    assert json.dumps(detail["pm_policy"])  # serialisable as sent to PM
