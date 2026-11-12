"""UAT and production apps have their own keys.

A participant creates UAT apps; once approved for production, "Move to production"
makes a production copy of a UAT app (same products) that waits for an administrator
and gets its own API key + secret. Each app lives in one environment: its clients /
consumer go to that environment's Keycloak and gateway - production's own when
KEYCLOAK_PROD_URL / GATEWAY_PROD_ADMIN_URL are set, else the main ones - and its
tokens name only that environment."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import settings
from app.core.exceptions import UpstreamError
from app.integrations import gateway, keycloak, keycloak_oidc
from app.integrations.gateway import GatewayRoute, GatewaySnapshot
from app.models.participant import Participant
from app.services import app_gateway_service
from tests import test_apps
from tests.test_apps import (
    FARMER_PATHS,
    _admin_row,
    _api_product,
    _approve_app,
    _create_app,
    _routes,
)

farmer_endpoints = test_apps.farmer_endpoints  # fixture

KEYS = {env: rsa.generate_private_key(public_exponent=65537, key_size=2048) for env in ("UAT", "PRODUCTION")}
HEADER = "X-Partner-Token"


def _production_routes() -> list[GatewayRoute]:
    """Production's gateway: its own route ids, and no route for the search path."""
    return [GatewayRoute(id="p-summary", name="summary", service_key=None, paths=[FARMER_PATHS[0]], methods=["POST"])]


class FakeRealms:
    """App clients per Keycloak realm (keycloak.current_realm()), with their tokens."""

    def __init__(self):
        self.clients: dict[str, dict[str, dict]] = {"UAT": {}, "PRODUCTION": {}}
        self.token_urls: list[str] = []

    def install(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "oauth")
        monkeypatch.setattr(settings, "KEYCLOAK_URL", "http://keycloak.uat.internal:8080")
        monkeypatch.setattr(settings, "KEYCLOAK_PUBLIC_URL", "https://keycloak.uat.example.org")
        monkeypatch.setattr(settings, "KEYCLOAK_REALM", "partner")
        monkeypatch.setattr(settings, "KEYCLOAK_JWKS_URL", "")
        monkeypatch.setattr(keycloak, "upsert_app_client", self.upsert)
        monkeypatch.setattr(keycloak, "delete_app_client", self.delete)
        monkeypatch.setattr(keycloak, "request_app_token", self.token)
        monkeypatch.setattr(keycloak_oidc, "_jwks_client", lambda: self)
        return self

    @staticmethod
    def realm() -> str:
        return keycloak.current_realm().environment

    def upsert(self, client_id, secret, app_uid, description, claims):
        self.clients[self.realm()][client_id] = {"secret": secret, "claims": claims}

    def delete(self, client_id):
        self.clients[self.realm()].pop(client_id, None)

    def token(self, client_id, secret):
        realm = self.realm()
        self.token_urls.append(keycloak.token_url(public=False))
        client = self.clients[realm][client_id]
        assert client["secret"] == secret
        now = int(time.time())
        claims = {"iss": keycloak.current_realm().url, "exp": now + 300, "azp": client_id, **client["claims"]}
        return {"access_token": jwt.encode(claims, KEYS[realm], algorithm="RS256", headers={"kid": realm}),
                "token_type": "Bearer", "expires_in": 300}

    def get_signing_key_from_jwt(self, token):
        # The keys of the realm being asked (as PyJWKClient for that realm's certs URL).
        realm = self.realm()
        if jwt.get_unverified_header(token).get("kid") != realm:
            raise jwt.PyJWKClientError("Unable to find a signing key that matches")
        return jwt.PyJWK.from_dict({**jwt.algorithms.RSAAlgorithm.to_jwk(KEYS[realm].public_key(), as_dict=True),
                                    "kid": realm, "alg": "RS256"})

    def where(self, key: str) -> list[str]:
        return [realm for realm, clients in self.clients.items() if key in clients]


class FakeGateways:
    """Routes and consumers per Admin API (gateway.current_target())."""

    def __init__(self):
        self.routes = {"UAT": _routes(), "PRODUCTION": _production_routes()}
        self.consumers: dict[str, dict[str, dict]] = {"UAT": {}, "PRODUCTION": {}}

    def install(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", True)
        monkeypatch.setattr(settings, "GATEWAY_ADMIN_URL", "http://apisix.uat:9180")
        monkeypatch.setattr(settings, "GATEWAY_TYPE", "apisix")
        monkeypatch.setattr(gateway, "list_routes", lambda: self.routes[self.target()])
        monkeypatch.setattr(gateway, "put_consumer", self.put_consumer)
        monkeypatch.setattr(gateway, "delete_consumer", lambda username: self.consumers[self.target()].pop(username, None))
        monkeypatch.setattr(gateway, "put_credential", lambda *args: None)
        monkeypatch.setattr(gateway, "delete_credential", lambda *args: None)
        monkeypatch.setattr(gateway, "list_credential_ids", lambda username: [])
        return self

    @staticmethod
    def target() -> str:
        return gateway.current_target().environment

    def put_consumer(self, username, description, labels, plugins):
        self.consumers[self.target()][username] = {"labels": labels, "plugins": plugins}


@pytest.fixture
def realms(monkeypatch):
    return FakeRealms().install(monkeypatch)


@pytest.fixture
def gateways(monkeypatch):
    return FakeGateways().install(monkeypatch)


def own_keycloak(monkeypatch):
    monkeypatch.setattr(settings, "KEYCLOAK_PROD_URL", "http://keycloak.prod.internal:8080")
    monkeypatch.setattr(settings, "KEYCLOAK_PROD_PUBLIC_URL", "https://keycloak.prod.example.org")
    monkeypatch.setattr(settings, "KEYCLOAK_PROD_ADMIN_CLIENT_SECRET", "prod-provisioner-secret")


def own_gateway(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_PROD_ADMIN_URL", "http://apisix.prod:9180")
    monkeypatch.setattr(settings, "GATEWAY_PROD_ADMIN_TOKEN", "prod-viewer-key")


def set_production_access(db_session, approved: bool = True) -> Participant:
    owner = db_session.query(Participant).filter_by(email_id="partner@example.org").one()
    owner.is_prod_approved = owner.is_prod_enabled = approved
    db_session.commit()
    app_gateway_service.sync_participant_apps(db_session, owner.participant_id)
    return owner


def uat_app(client, admin_headers, participant_headers, farmer_endpoints) -> dict:
    """An approved UAT app with an automatic product (search + summary)."""
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    return _create_app(client, participant_headers, "Server App", [read], admin_headers)


def promote(client, participant_headers, uid):
    return client.post(f"/oan/participant/apps/{uid}/promote", headers=participant_headers)


def production_app(client, admin_headers, participant_headers, uid) -> dict:
    """Move a UAT app to production and let the administrator approve it."""
    response = promote(client, participant_headers, uid)
    assert response.status_code == 201, response.text
    return _approve_app(client, admin_headers, participant_headers, response.json()["data"]["app"]["app_id"])


def test_uat_app_works_only_on_uat_even_for_production_participants(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways
):
    key = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["credential"]["api_key"]
    set_production_access(db_session)

    claims = realms.clients["UAT"][key]["claims"]
    assert claims["oan_environments"] == ["uat"]  # no longer "production" too
    assert claims["oan_routes"] == ["r-search", "r-summary"]
    assert realms.where(key) == ["UAT"]


def test_move_to_production_needs_production_access_and_an_administrator(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways
):
    created = uat_app(client, admin_headers, participant_headers, farmer_endpoints)
    uid = created["app"]["app_id"]
    assert promote(client, participant_headers, uid).status_code == 403  # not approved for production

    set_production_access(db_session)
    response = promote(client, participant_headers, uid)
    assert response.status_code == 201, response.text
    prod = response.json()["data"]
    assert prod["credential"] is None
    assert prod["app"]["environment"] == "PRODUCTION" and prod["app"]["name"] == "Server App"
    assert prod["app"]["status_label"] == "Awaiting approval"
    # The product is automatic on UAT, but production always waits for an administrator.
    assert [p["status_label"] for p in prod["app"]["products"]] == ["Pending approval"]
    assert promote(client, participant_headers, uid).status_code == 409  # one production copy per name
    assert promote(client, participant_headers, prod["app"]["app_id"]).status_code in (400, 403)

    approved = _approve_app(client, admin_headers, participant_headers, prod["app"]["app_id"])
    prod_key, uat_key = approved["credential"]["api_key"], created["credential"]["api_key"]
    assert prod_key != uat_key and approved["credential"]["api_secret"] != created["credential"]["api_secret"]
    # One Keycloak for both (no production settings): its own client, naming only production.
    assert realms.clients["UAT"][prod_key]["claims"]["oan_environments"] == ["production"]
    assert realms.clients["UAT"][uat_key]["claims"]["oan_environments"] == ["uat"]


def test_production_requests_on_a_production_app_wait_for_an_administrator(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways
):
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod = production_app(client, admin_headers, participant_headers, uid)
    extra = _api_product(client, admin_headers, "farmer-extra", farmer_endpoints[2:3], approval="AUTO")
    response = client.post(f"/oan/participant/apps/{prod['app']['app_id']}/products", headers=participant_headers,
                           json={"api_product_ids": [extra]})
    assert response.status_code == 200, response.text
    statuses = {p["name"]: p["status_label"] for p in response.json()["data"]["products"]}
    assert statuses["farmer-extra"] == "Pending approval"


def test_production_keycloak_holds_only_production_apps(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways, monkeypatch
):
    own_keycloak(monkeypatch)
    created = uat_app(client, admin_headers, participant_headers, farmer_endpoints)
    set_production_access(db_session)
    prod = production_app(client, admin_headers, participant_headers, created["app"]["app_id"])
    uat_key, prod_key = created["credential"]["api_key"], prod["credential"]["api_key"]

    assert realms.where(uat_key) == ["UAT"] and realms.where(prod_key) == ["PRODUCTION"]
    assert realms.clients["PRODUCTION"][prod_key]["claims"]["oan_environments"] == ["production"]

    # Production access taken away: the production app's clients go, the UAT app stays.
    set_production_access(db_session, approved=False)
    assert realms.where(prod_key) == [] and realms.where(uat_key) == ["UAT"]
    set_production_access(db_session)
    assert realms.where(prod_key) == ["PRODUCTION"]
    assert client.delete(f"/oan/participant/apps/{prod['app']['app_id']}", headers=participant_headers).status_code == 200
    assert realms.where(prod_key) == [] and realms.where(uat_key) == ["UAT"]


def test_production_app_written_before_its_keycloak_existed_moves_there(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways, monkeypatch
):
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod_key = production_app(client, admin_headers, participant_headers, uid)["credential"]["api_key"]
    assert realms.where(prod_key) == ["UAT"]  # one Keycloak for both, so far

    own_keycloak(monkeypatch)
    set_production_access(db_session)  # any re-sync
    assert realms.where(prod_key) == ["PRODUCTION"]


def test_get_token_comes_from_the_apps_keycloak(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways, monkeypatch
):
    own_keycloak(monkeypatch)
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod_uid = production_app(client, admin_headers, participant_headers, uid)["app"]["app_id"]

    uat = client.post(f"/oan/participant/apps/{uid}/token", headers=participant_headers).json()["data"]
    prod = client.post(f"/oan/participant/apps/{prod_uid}/token", headers=participant_headers).json()["data"]
    assert uat["token_url"] == "https://keycloak.uat.example.org/realms/partner/protocol/openid-connect/token"
    assert prod["token_url"] == "https://keycloak.prod.example.org/realms/partner/protocol/openid-connect/token"
    assert realms.token_urls == [
        "http://keycloak.uat.internal:8080/realms/partner/protocol/openid-connect/token",
        "http://keycloak.prod.internal:8080/realms/partner/protocol/openid-connect/token",
    ]
    # Each token is checked with its own realm's keys before its claims are shown.
    assert uat["claims"]["oan_environments"] == ["uat"]
    assert prod["claims"]["oan_environments"] == ["production"]

    set_production_access(db_session, approved=False)
    assert client.post(f"/oan/participant/apps/{prod_uid}/token", headers=participant_headers).status_code == 403


def test_production_gateway_routes_go_into_production_apps(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways, monkeypatch
):
    own_keycloak(monkeypatch)
    own_gateway(monkeypatch)
    created = uat_app(client, admin_headers, participant_headers, farmer_endpoints)
    set_production_access(db_session)
    prod = production_app(client, admin_headers, participant_headers, created["app"]["app_id"])

    assert realms.clients["UAT"][created["credential"]["api_key"]]["claims"]["oan_routes"] == ["r-search", "r-summary"]
    assert realms.clients["PRODUCTION"][prod["credential"]["api_key"]]["claims"]["oan_routes"] == ["p-summary"]
    row = _admin_row(client, admin_headers, prod["app"]["app_id"])
    assert row["gateway_status"] == "SYNCED" and row["gateway_routes"] == ["p-summary"]
    assert any(FARMER_PATHS[1] in w for w in row["gateway_warnings"])  # production has no search route
    assert gateways.consumers == {"UAT": {}, "PRODUCTION": {}}  # oauth: nothing written


def test_unreachable_production_gateway_fails_only_production_apps(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways, monkeypatch
):
    own_gateway(monkeypatch)
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod_uid = production_app(client, admin_headers, participant_headers, uid)["app"]["app_id"]

    def routes():
        if gateway.current_target().environment == "PRODUCTION":
            raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_PROD_ADMIN_URL.")
        return _routes()

    monkeypatch.setattr(gateway, "list_routes", routes)
    set_production_access(db_session)
    assert _admin_row(client, admin_headers, uid)["gateway_status"] == "SYNCED"
    prod = _admin_row(client, admin_headers, prod_uid)
    assert prod["gateway_status"] == "FAILED" and "GATEWAY_PROD_ADMIN_URL" in prod["gateway_error"]


def test_apikey_mode_production_app_is_a_consumer_on_productions_gateway(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, gateways, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "apikey")
    own_gateway(monkeypatch)
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod_uid = production_app(client, admin_headers, participant_headers, uid)["app"]["app_id"]
    uat_consumer, prod_consumer = ("oanapp_" + u.replace("-", "") for u in (uid, prod_uid))

    assert set(gateways.consumers["UAT"]) == {uat_consumer}
    assert set(gateways.consumers["PRODUCTION"]) == {prod_consumer}
    prod = gateways.consumers["PRODUCTION"][prod_consumer]
    assert prod["labels"]["environment"] == "production"
    assert prod["plugins"]["consumer-restriction"]["whitelist"] == ["p-summary"]

    set_production_access(db_session, approved=False)
    assert gateways.consumers["PRODUCTION"] == {} and set(gateways.consumers["UAT"]) == {uat_consumer}


def test_try_it_uses_an_app_of_the_chosen_environment(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways, monkeypatch
):
    from app.services import sandbox_service

    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.uat:9080")
    monkeypatch.setattr(settings, "GATEWAY_PROD_URL", "http://apisix.prod:9080")
    calls = []
    monkeypatch.setattr(sandbox_service, "_call_upstream",
                        lambda method, url, headers, body: calls.append(url) or (200, {}, {"ok": True}, None))
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod_uid = production_app(client, admin_headers, participant_headers, uid)["app"]["app_id"]

    def run(app_uid, environment):
        return client.post("/oan/participant/try-it", headers=participant_headers, json={
            "endpoint_id": farmer_endpoints[0], "app_id": app_uid, "environment": environment,
            "body": {}, "headers": {HEADER: "token"}})

    assert run(uid, "UAT").status_code == 200
    assert run(prod_uid, "PRODUCTION").status_code == 200
    wrong = run(uid, "PRODUCTION")
    assert wrong.status_code == 400 and "UAT app" in wrong.json()["message"]
    assert run(prod_uid, "UAT").status_code == 400
    assert [url.split("/farmer")[0].split("/register")[0] for url in calls] == [
        "http://apisix.uat:9080", "http://apisix.prod:9080"]


def test_pull_reads_the_chosen_gateway(client, admin_headers, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_ADMIN_URL", "http://apisix.uat:9180")
    read: list[str] = []
    monkeypatch.setattr(gateway, "fetch", lambda: read.append(gateway.current_target().url) or GatewaySnapshot("apisix", [], []))

    status = client.get("/oan/admin/gateway/status", headers=admin_headers).json()["data"]
    assert status["environments"] == ["UAT"]
    client.post("/oan/admin/gateway/sync", headers=admin_headers, json={"dry_run": True})

    own_gateway(monkeypatch)
    status = client.get("/oan/admin/gateway/status", headers=admin_headers).json()["data"]
    assert status["environments"] == ["UAT", "PRODUCTION"]
    report = client.post("/oan/admin/gateway/sync", headers=admin_headers,
                         json={"dry_run": True, "environment": "PRODUCTION"}).json()["data"]
    assert report["environment"] == "PRODUCTION"
    assert read == ["http://apisix.uat:9180", "http://apisix.prod:9180"]


def test_production_keycloak_needs_its_service_account_secret():
    from pydantic import ValidationError

    from app.config.settings import Settings

    with pytest.raises(ValidationError, match="KEYCLOAK_PROD_ADMIN_CLIENT_SECRET"):
        Settings(KEYCLOAK_PROD_URL="http://keycloak.prod:8080", KEYCLOAK_PROD_ADMIN_CLIENT_SECRET="")


def test_production_app_can_have_its_own_ip_whitelist(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways
):
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    assert client.put(f"/oan/participant/apps/{uid}", headers=participant_headers, json={
        "allowed_ips": ["10.0.0.5"]}).status_code == 200
    set_production_access(db_session)
    url = f"/oan/participant/apps/{uid}/promote"

    bad_ip = client.post(url, headers=participant_headers, json={"allowed_ips": ["not-an-ip"]})
    assert bad_ip.status_code == 400 and "not an IP address" in bad_ip.json()["message"]

    response = client.post(url, headers=participant_headers, json={
        "allowed_ips": ["203.0.113.10", "198.51.100.0/24"],
        "description": "Production servers"})
    assert response.status_code == 201, response.text
    prod = response.json()["data"]["app"]
    assert "callback_url" not in prod  # the field is gone: nothing ever called it
    assert prod["allowed_ips"] == ["203.0.113.10", "198.51.100.0/24"]
    assert prod["description"] == "Production servers"
    uat = client.get(f"/oan/participant/apps/{uid}", headers=participant_headers).json()["data"]
    assert uat["allowed_ips"] == ["10.0.0.5"]


def test_admin_can_list_uat_or_production_apps(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, gateways
):
    uid = uat_app(client, admin_headers, participant_headers, farmer_endpoints)["app"]["app_id"]
    set_production_access(db_session)
    prod_uid = production_app(client, admin_headers, participant_headers, uid)["app"]["app_id"]

    def ids(**query):
        rows = client.post("/oan/admin/apps/list", headers=admin_headers, json=query).json()["data"]["apps"]
        return {row["app_id"] for row in rows}

    assert ids() == {uid, prod_uid}
    assert ids(environment="UAT") == {uid}
    assert ids(environment="PRODUCTION") == {prod_uid}
    assert ids(filters={"environment": "production"}) == {prod_uid}
