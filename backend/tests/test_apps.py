"""API products, participant apps, their keys and the gateway consumer they become.

A new app waits for an administrator and has no key; ``_create_app`` with
``admin_headers`` approves it straight away and returns the owner's view
(app + first key), which is what most tests need.
"""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.core import crypto
from app.integrations import gateway
from app.integrations.gateway import GatewayRoute
from app.models.app import ParticipantAppCredential
from app.models.catalog import Endpoint, Product
from app.models.logs import ApiLog
from app.models.participant import Participant
from tests.conftest import PARTICIPANT_PASSWORD

FARMER_PATHS = [
    "/farmer-registry/register-data/get_register_summary_data",
    "/farmer-registry/register-data/search_in_a_register",
    "/farmer-registry/register-data/get_subject_record",
    "/farmer-registry/intake-form-data/save_intake_form_submission",
]


class FakeGateway:
    """Records what the sandbox writes to APISIX."""

    def __init__(self, routes: list[GatewayRoute]):
        self.routes = routes
        self.consumers: dict[str, dict] = {}
        self.credentials: dict[str, dict[str, dict]] = {}

    def install(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", True)
        monkeypatch.setattr(settings, "GATEWAY_ADMIN_URL", "http://apisix.test:9180")
        monkeypatch.setattr(settings, "GATEWAY_TYPE", "apisix")
        monkeypatch.setattr(gateway, "list_routes", lambda: self.routes)
        monkeypatch.setattr(gateway, "put_consumer", self.put_consumer)
        monkeypatch.setattr(gateway, "delete_consumer", self.delete_consumer)
        monkeypatch.setattr(gateway, "put_credential", self.put_credential)
        monkeypatch.setattr(gateway, "delete_credential", self.delete_credential)
        monkeypatch.setattr(gateway, "list_credential_ids", lambda u: list(self.credentials.get(u, {})))
        return self

    def put_consumer(self, username, description, labels, plugins):
        self.consumers[username] = {"labels": labels, "plugins": plugins}
        self.credentials.setdefault(username, {})

    def delete_consumer(self, username):
        self.consumers.pop(username, None)
        self.credentials.pop(username, None)

    def put_credential(self, username, credential_id, description, plugins):
        self.credentials[username][credential_id] = plugins

    def delete_credential(self, username, credential_id):
        self.credentials[username].pop(credential_id, None)

    def whitelist(self, username) -> list[str]:
        return self.consumers[username]["plugins"]["consumer-restriction"]["whitelist"]


@pytest.fixture
def farmer_endpoints(db_session) -> list[int]:
    product = Product(
        product_name="Farmer Registry", is_published=True, is_gateway_published=True, country_code="ET"
    )
    db_session.add(product)
    db_session.flush()
    endpoints = [
        Endpoint(product_id=product.product_id, method="POST", endpoint_url=path, display_name=path.rsplit("/", 1)[-1],
                 is_published=True, country_code="ET")
        for path in FARMER_PATHS
    ]
    db_session.add_all(endpoints)
    db_session.commit()
    return [e.endpoint_id for e in endpoints]


def _routes() -> list[GatewayRoute]:
    """One route per read operation, and one route serving two paths."""
    return [
        GatewayRoute(id="r-summary", name="summary", service_key=None, paths=[FARMER_PATHS[0]], methods=["POST"]),
        GatewayRoute(id="r-search", name="search", service_key=None, paths=[FARMER_PATHS[1]], methods=["POST"]),
        GatewayRoute(id="r-mixed", name="mixed", service_key=None, paths=FARMER_PATHS[2:], methods=["POST"]),
    ]


def _api_product(client, admin_headers, name, endpoint_ids, approval="AUTO", published=True) -> int:
    response = client.post(
        "/oan/admin/api-products",
        headers=admin_headers,
        json={
            "name": name,
            "display_name": name.replace("-", " ").title(),
            "approval_type": approval,
            "is_published": published,
            "endpoint_ids": endpoint_ids,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["api_product_id"]


def _create_app(client, participant_headers, name, product_ids, admin_headers=None):
    """Create an app; with ``admin_headers`` the administrator approves it at once."""
    response = client.post(
        "/oan/participant/apps",
        headers=participant_headers,
        json={"name": name, "description": "test", "api_product_ids": product_ids},
    )
    assert response.status_code == 201, response.text
    created = response.json()["data"]
    if admin_headers is None:
        return created
    return _approve_app(client, admin_headers, participant_headers, created["app"]["app_id"])


def _admin_row(client, admin_headers, app_uid) -> dict:
    consumer = "oanapp_" + app_uid.replace("-", "")
    rows = client.post("/oan/admin/apps/list", headers=admin_headers, json={"search": consumer}).json()["data"]["apps"]
    [row] = [r for r in rows if r["app_id"] == app_uid]
    return row


def _approve_app(client, admin_headers, participant_headers, app_uid, remarks=None):
    """The administrator approves the whole app; returns the owner's view: app + its first key."""
    row = _admin_row(client, admin_headers, app_uid)
    approved = client.post(f"/oan/admin/apps/{row['id']}/approve", headers=admin_headers, json={"remarks": remarks})
    assert approved.status_code == 200, approved.text
    app = client.get(f"/oan/participant/apps/{app_uid}", headers=participant_headers).json()["data"]
    return {"app": app, "credential": app["credentials"][0]}


# ------------------------------------------------------------- API products
def test_api_product_crud_and_endpoint_mapping(client, admin_headers, farmer_endpoints):
    pid = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2], published=False)
    detail = client.get(f"/oan/admin/api-products/{pid}", headers=admin_headers).json()["data"]
    assert detail["endpoint_count"] == 2
    assert [e["endpoint_id"] for e in detail["endpoints"]] == farmer_endpoints[:2]

    # The same endpoint may sit in several API products.
    _api_product(client, admin_headers, "farmer-full", farmer_endpoints)

    duplicate = client.post(
        "/oan/admin/api-products",
        headers=admin_headers,
        json={"name": "farmer-read", "display_name": "Again", "endpoint_ids": []},
    )
    assert duplicate.status_code == 409

    bad = client.post(
        "/oan/admin/api-products",
        headers=admin_headers,
        json={"name": "Bad Name!", "display_name": "x", "endpoint_ids": []},
    )
    assert bad.status_code == 400

    unknown = client.put(
        f"/oan/admin/api-products/{pid}",
        headers=admin_headers,
        json={"name": "farmer-read", "display_name": "Read", "endpoint_ids": [999_999]},
    )
    assert unknown.status_code == 400

    options = client.get("/oan/admin/api-products/endpoint-options", headers=admin_headers).json()["data"]
    assert len(options[0]["endpoints"]) == 4


def test_participants_see_only_published_api_products(
    client, admin_headers, participant_headers, farmer_endpoints
):
    _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    _api_product(client, admin_headers, "farmer-draft", farmer_endpoints, published=False)
    products = client.get("/oan/participant/api-products", headers=participant_headers).json()["data"]
    assert [p["name"] for p in products] == ["farmer-read"]
    assert len(products[0]["endpoints"]) == 2


# --------------------------------------------------------------------- apps
def test_new_app_waits_for_approval_without_a_key(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    sent = []
    monkeypatch.setattr("app.services.app_service.send_templated", lambda db, code, to, values: sent.append((code, to, values)) or True)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])

    created = _create_app(client, participant_headers, "Mobile App", [read])
    app = created["app"]
    assert created["credential"] is None
    assert (app["status"], app["status_label"]) == (0, "Awaiting approval")
    assert app["credentials"] == [] and db_session.query(ParticipantAppCredential).count() == 0
    assert app["gateway_consumer"] not in fake.consumers  # nothing at the gateway yet

    # No key can be issued, and the app cannot call anything, before the decision.
    blocked = client.post(f"/oan/participant/apps/{app['app_id']}/credentials", headers=participant_headers)
    assert blocked.status_code == 403 and "awaiting approval" in blocked.text
    # Requesting more products is allowed while waiting.
    more = _api_product(client, admin_headers, "farmer-more", farmer_endpoints[2:], approval="MANUAL")
    asked = client.post(f"/oan/participant/apps/{app['app_id']}/products", headers=participant_headers,
                        json={"api_product_ids": [more]})
    assert asked.status_code == 200, asked.text

    # The console lists it among the apps awaiting a decision.
    pending = client.post("/oan/admin/apps/list", headers=admin_headers, json={"pending_only": True}).json()["data"]
    assert [a["app_id"] for a in pending["apps"]] == [app["app_id"]]
    assert pending["apps"][0]["credentials"] == []

    # Approving the app grants its open requests and issues the first key.
    approved = client.post(f"/oan/admin/apps/{pending['apps'][0]['id']}/approve", headers=admin_headers,
                           json={"remarks": "Welcome"}).json()["data"]
    assert approved["status_label"] == "Active"
    assert {p["name"]: p["status_label"] for p in approved["products"]} == {"farmer-read": "Approved", "farmer-more": "Approved"}
    assert len(approved["credentials"]) == 1 and approved["credentials"][0]["api_key"] is None  # admins never see keys
    assert [s[0] for s in sent] == ["APP_APPROVED"] and sent[0][2]["app_name"] == "Mobile App"
    assert client.post("/oan/admin/apps/list", headers=admin_headers, json={"pending_only": True}).json()["data"]["apps"] == []


def test_rejected_app_gets_no_key_and_can_be_approved_later(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    sent = []
    monkeypatch.setattr("app.services.app_service.send_templated", lambda db, code, to, values: sent.append((code, values)) or True)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2], approval="MANUAL")
    app = _create_app(client, participant_headers, "Doubtful", [read])["app"]
    row = _admin_row(client, admin_headers, app["app_id"])

    rejected = client.post(f"/oan/admin/apps/{row['id']}/reject", headers=admin_headers,
                           json={"reason": "Unknown organisation"}).json()["data"]
    assert (rejected["status_label"], rejected["revoked_reason"]) == ("Rejected", "Unknown organisation")
    assert rejected["products"][0]["status_label"] == "Rejected"
    assert db_session.query(ParticipantAppCredential).count() == 0 and fake.consumers == {}
    assert sent[-1][0] == "APP_REJECTED" and sent[-1][1]["reason"] == "Unknown organisation"
    mine = client.get(f"/oan/participant/apps/{app['app_id']}", headers=participant_headers).json()["data"]
    assert mine["status"] == 3 and mine["revoked_reason"] == "Unknown organisation"
    blocked = client.post(f"/oan/participant/apps/{app['app_id']}/credentials", headers=participant_headers)
    assert blocked.status_code == 403 and "rejected" in blocked.text
    # A rejected app cannot be "revoked" or "restored": those are for active / revoked apps.
    assert client.post(f"/oan/admin/apps/{row['id']}/revoke", headers=admin_headers, json={"reason": "x"}).status_code == 400
    assert client.post(f"/oan/admin/apps/{row['id']}/restore", headers=admin_headers).status_code == 400
    assert client.post(f"/oan/admin/apps/{row['id']}/reject", headers=admin_headers, json={"reason": "again"}).status_code == 400

    # Second thoughts: approving it now works like any approval.
    owner = _approve_app(client, admin_headers, participant_headers, app["app_id"])
    assert owner["app"]["status_label"] == "Active" and owner["credential"]["api_key"].startswith("oan_")
    assert owner["app"]["products"][0]["status_label"] == "Approved"


def test_approved_app_has_encrypted_key_and_provisions_gateway(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])

    created = _create_app(client, participant_headers, "Mobile App", [read], admin_headers)
    app, credential = created["app"], created["credential"]

    assert credential["api_key"].startswith("oan_")
    assert len(credential["api_secret"]) >= 40
    assert app["status_label"] == "Active"
    assert app["products"][0]["status_label"] == "Approved"  # AUTO approval
    assert app["gateway_status"] == "SYNCED"

    # Stored encrypted and hashed, never in clear.
    row = db_session.query(ParticipantAppCredential).one()
    assert credential["api_key"] not in row.api_key_encrypted
    assert credential["api_secret"] not in row.api_secret_encrypted
    assert row.api_key_hash == crypto.sha256_hex(credential["api_key"])
    assert crypto.decrypt(row.api_secret_encrypted) == credential["api_secret"]

    # The owner reads key and secret from the app; administrators get neither.
    listed = client.get("/oan/participant/apps", headers=participant_headers).json()["data"][0]
    assert listed["credentials"][0]["api_key"] == credential["api_key"]
    assert listed["credentials"][0]["api_secret"] == credential["api_secret"]
    assert listed["credentials"][0]["api_secret_hint"] == "••••" + credential["api_secret"][-4:]
    admin_view = _admin_row(client, admin_headers, app["app_id"])
    assert admin_view["credentials"][0]["api_key"] is None and admin_view["credentials"][0]["api_secret"] is None
    assert credential["api_secret"] not in str(admin_view)

    consumer = app["gateway_consumer"]
    assert fake.whitelist(consumer) == ["r-search", "r-summary"]
    plugins = fake.credentials[consumer]
    key_id = f"{credential['credential_id']}-key"
    assert plugins[key_id] == {"key-auth": {"key": credential["api_key"]}}
    assert plugins[f"{credential['credential_id']}-hmac"]["hmac-auth"]["secret_key"] == credential["api_secret"]
    assert fake.consumers[consumer]["labels"]["app_uid"] == app["app_id"]
    # The owner as its Keycloak token names it: the gateway binds the key to the partner token.
    owner = db_session.get(Participant, int(fake.consumers[consumer]["labels"]["participant_id"]))
    assert fake.consumers[consumer]["labels"]["participant_uid"] == str(owner.unique_id)


def test_route_serving_endpoints_outside_the_products_is_not_granted(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    # Only one of the two paths the "mixed" route serves.
    partial = _api_product(client, admin_headers, "farmer-record", [farmer_endpoints[2]])
    app = _create_app(client, participant_headers, "Partial", [partial], admin_headers)["app"]

    assert fake.whitelist(app["gateway_consumer"]) == ["oan-sandbox-no-route"]
    assert "Route 'mixed'" in app["gateway_warnings"][0]


def test_manual_product_waits_for_admin_and_admin_decisions_resync(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    full = _api_product(client, admin_headers, "farmer-full", farmer_endpoints, approval="MANUAL")
    app = _create_app(client, participant_headers, "Portal", [full])["app"]
    consumer = app["gateway_consumer"]
    assert app["products"][0]["status_label"] == "Pending approval"
    assert app["status_label"] == "Awaiting approval" and consumer not in fake.consumers

    pending = client.post(
        "/oan/admin/apps/list", headers=admin_headers, json={"pending_only": True}
    ).json()["data"]
    assert pending["pagination"]["total"] == 1
    admin_app = pending["apps"][0]
    assert admin_app["participant_email"] == "partner@example.org"
    assert admin_app["credentials"] == []  # no key before a decision

    # Approving one product of a waiting app is its approval: active, first key issued.
    approved = client.post(
        f"/oan/admin/apps/{admin_app['id']}/products/{full}/approve", headers=admin_headers, json={}
    ).json()["data"]
    assert approved["products"][0]["status_label"] == "Approved"
    assert approved["status_label"] == "Active" and len(approved["credentials"]) == 1
    assert approved["credentials"][0]["api_key"] is None  # admins never see keys
    assert fake.whitelist(consumer) == ["r-mixed", "r-search", "r-summary"]

    revoked = client.post(
        f"/oan/admin/apps/{admin_app['id']}/products/{full}/revoke",
        headers=admin_headers,
        json={"remarks": "Misuse"},
    )
    assert revoked.status_code == 200
    assert fake.whitelist(consumer) == ["oan-sandbox-no-route"]

    # Re-requesting revoked access goes back to the administrator, not AUTO.
    again = client.post(
        f"/oan/participant/apps/{app['app_id']}/products",
        headers=participant_headers,
        json={"api_product_ids": [full]},
    ).json()["data"]
    assert again["products"][0]["status_label"] == "Pending approval"

    # A rejection cannot be applied to an approved grant.
    client.post(f"/oan/admin/apps/{admin_app['id']}/products/{full}/approve", headers=admin_headers, json={})
    wrong = client.post(
        f"/oan/admin/apps/{admin_app['id']}/products/{full}/reject",
        headers=admin_headers,
        json={"remarks": "late"},
    )
    assert wrong.status_code == 400


def test_key_rotation_limits_and_revocation(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Rotate", [read], admin_headers)
    uid, first = created["app"]["app_id"], created["credential"]["credential_id"]
    consumer = created["app"]["gateway_consumer"]

    second = client.post(f"/oan/participant/apps/{uid}/credentials", headers=participant_headers)
    assert second.status_code == 201
    assert len(fake.credentials[consumer]) == 4
    third = client.post(f"/oan/participant/apps/{uid}/credentials", headers=participant_headers)
    assert third.status_code == 400

    revoked = client.delete(f"/oan/participant/apps/{uid}/credentials/{first}", headers=participant_headers)
    assert revoked.status_code == 200
    assert set(fake.credentials[consumer]) == {
        f"{second.json()['data']['credential_id']}-key",
        f"{second.json()['data']['credential_id']}-hmac",
    }
    states = {c["credential_id"]: c["status_label"] for c in revoked.json()["data"]["credentials"]}
    assert states[first] == "Revoked"


def test_admin_revoke_and_delete_remove_the_consumer(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    app = _create_app(client, participant_headers, "Gone", [read], admin_headers)["app"]
    consumer = app["gateway_consumer"]
    admin_id = client.post("/oan/admin/apps/list", headers=admin_headers, json={}).json()["data"]["apps"][0]["id"]

    client.post(f"/oan/admin/apps/{admin_id}/revoke", headers=admin_headers, json={"reason": "Abuse"})
    assert consumer not in fake.consumers
    blocked = client.post(f"/oan/participant/apps/{app['app_id']}/credentials", headers=participant_headers)
    assert blocked.status_code == 403

    client.post(f"/oan/admin/apps/{admin_id}/restore", headers=admin_headers)
    assert consumer in fake.consumers

    assert client.delete(f"/oan/participant/apps/{app['app_id']}", headers=participant_headers).status_code == 200
    assert consumer not in fake.consumers
    assert client.get("/oan/participant/apps", headers=participant_headers).json()["data"] == []


def test_gateway_failure_is_recorded_not_raised(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    from app.core.exceptions import UpstreamError

    FakeGateway(_routes()).install(monkeypatch)

    def down():
        raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL.")

    monkeypatch.setattr(gateway, "list_routes", down)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    app = _create_app(client, participant_headers, "Offline", [read], admin_headers)["app"]
    assert app["gateway_status"] == "FAILED"
    # The participant gets a plain message; the Admin API detail is for administrators.
    assert "GATEWAY_ADMIN_URL" not in app["gateway_error"]
    rows = client.post(
        "/oan/admin/apps/list", headers=admin_headers, json={"search": "Offline"}
    ).json()["data"]
    rows = rows.get("apps", rows.get("rows", [])) if isinstance(rows, dict) else rows
    assert any("could not be reached" in (row.get("gateway_error") or "") for row in rows)


def test_apps_without_gateway_sync_are_kept_in_the_sandbox(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    app = _create_app(client, participant_headers, "Local", [read], admin_headers)["app"]
    assert app["gateway_status"] == "DISABLED"


def test_app_name_rules_and_ownership(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    app = _create_app(client, participant_headers, "Mine", [read], admin_headers)["app"]
    dup = client.post("/oan/participant/apps", headers=participant_headers, json={"name": "mine"})
    assert dup.status_code == 409
    unpublished = _api_product(client, admin_headers, "hidden", farmer_endpoints, published=False)
    hidden = client.post(
        "/oan/participant/apps", headers=participant_headers, json={"name": "Other", "api_product_ids": [unpublished]}
    )
    assert hidden.status_code == 400

    # Another participant cannot see or touch the app.
    from app.core.security import hash_password

    other = Participant(
        first_name="Other", email_id="other@example.org", user_pass=hash_password(PARTICIPANT_PASSWORD),
        country_code="ET", is_email_verified=True, is_approved=1, is_activated=1, is_uat_requested=True, is_uat_approved=True,
    )
    db_session.add(other)
    db_session.commit()
    login = client.post(
        "/oan/participant/auth/login", json={"email_id": other.email_id, "password": PARTICIPANT_PASSWORD}
    ).json()["data"]
    headers = {"x-access-token": login["access_token"], "x-auth-key": login["auth_key"]}
    assert client.get(f"/oan/participant/apps/{app['app_id']}", headers=headers).status_code == 404
    assert client.delete(f"/oan/participant/apps/{app['app_id']}", headers=headers).status_code == 404


# ------------------------------------------------------------------- try-it
def test_try_it_as_app_sends_its_key_and_never_logs_it(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    from app.services import sandbox_service

    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.test:9080")
    calls = []

    def fake_call(method, url, headers, body):
        calls.append(headers)
        return 200, {}, {"ok": True}, None

    monkeypatch.setattr(sandbox_service, "_call_upstream", fake_call)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Console", [read], admin_headers)

    response = client.post(
        "/oan/participant/try-it",
        headers=participant_headers,
        json={"endpoint_id": farmer_endpoints[0], "app_id": created["app"]["app_id"], "body": {}},
    )
    assert response.status_code == 200, response.text
    assert calls[0]["apikey"] == created["credential"]["api_key"]
    logged = db_session.query(ApiLog).one()
    assert logged.request_headers["apikey"] == "***"


# -------------------------------------------------------------- code sample
def test_code_sample_follows_the_try_it_form_and_app_key(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.test:9080")
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Postman", [read], admin_headers)

    def sample(**form):
        response = client.post(
            "/oan/participant/code-sample",
            headers=participant_headers,
            json={"endpoint_id": farmer_endpoints[1], "language": "curl", "request": form} if form
            else {"endpoint_id": farmer_endpoints[1], "language": "curl"},
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]["code"]

    code = sample(
        headers={"X-CSRF-Token": "abc", "Authorization": "Bearer t", "apikey": "<typed>"},
        query_params={"page": 2, "empty": ""},
        body={"search_text": "maize"},
        app_id=created["app"]["app_id"],
    )
    assert f"-H 'apikey: {created['credential']['api_key']}'" in code
    assert "<typed>" not in code
    assert "-H 'X-CSRF-Token: abc'" in code and "-H 'Authorization: Bearer t'" in code
    assert "?page=2'" in code and "empty" not in code
    assert '"search_text": "maize"' in code

    no_body = sample(headers={}, has_body=False, body={"ignored": True})
    assert "-d " not in no_body

    # Without the form: the published sample, as before.
    assert "Authorization: Bearer <access_token>" in sample()
