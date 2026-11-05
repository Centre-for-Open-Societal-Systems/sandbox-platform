"""GATEWAY_PARTNER_AUTH=oauth: every active app key is also a Keycloak OAuth client
(client_id = API key, client_secret = API secret, client credentials only) whose access
token names the owner, the app, the approved environments and the app's routes. The
portal's "Get token" fetches it (POST /participant/apps/{id}/token) and try-it sends the
token in the form, never the key. Nothing is written to the gateway: the routes check
the token, so the sandbox only reads them (a viewer admin key is enough)."""

from __future__ import annotations

import time

import jwt
import pytest

from app.config.settings import settings
from app.integrations import keycloak
from app.models.participant import Participant
from app.utils import schema_tools
from tests import test_apps
from tests.test_apps import FakeGateway, _api_product, _create_app, _routes

HEADER = "X-Partner-Token"
farmer_endpoints = test_apps.farmer_endpoints  # fixture


class FakeKeycloakClients:
    """Keycloak's app clients and their client-credentials token endpoint."""

    def __init__(self):
        self.clients: dict[str, dict] = {}
        self.tokens_issued: list[str] = []

    def install(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "oauth")
        monkeypatch.setattr(keycloak, "upsert_app_client", self.upsert)
        monkeypatch.setattr(keycloak, "delete_app_client", lambda client_id: self.clients.pop(client_id, None))
        monkeypatch.setattr(keycloak, "request_app_token", self.token)
        return self

    def upsert(self, client_id, secret, app_uid, description, claims):
        self.clients[client_id] = {"secret": secret, "app_uid": app_uid, "claims": claims}

    def token(self, client_id, secret):
        assert self.clients[client_id]["secret"] == secret
        self.tokens_issued.append(client_id)
        now = int(time.time())
        claims = {"iss": "http://kc/realms/partner", "azp": client_id, "iat": now, "exp": now + 300,
                  "sub": "service-account", **self.clients[client_id]["claims"]}
        return {"access_token": jwt.encode(claims, "test-signing-key-of-32-bytes-or-more!", algorithm="HS256"),
                "token_type": "Bearer", "expires_in": 300}


def read_only(fake: FakeGateway, monkeypatch) -> list[str]:
    """Every gateway write the sandbox attempts (oauth mode: none)."""
    writes: list[str] = []
    for name in ("put_consumer", "delete_consumer", "put_credential", "delete_credential", "list_credential_ids"):
        monkeypatch.setattr(test_apps.gateway, name, lambda *a, _n=name: writes.append(_n))
    return writes


@pytest.fixture
def kc(monkeypatch):
    return FakeKeycloakClients().install(monkeypatch)


def test_approved_app_key_becomes_an_oauth_client(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, kc, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    writes = read_only(fake, monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])

    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)

    key, secret = created["credential"]["api_key"], created["credential"]["api_secret"]
    owner = db_session.query(Participant).filter_by(email_id="partner@example.org").one()
    assert set(kc.clients) == {key}
    assert kc.clients[key]["secret"] == secret
    claims = kc.clients[key]["claims"]
    assert claims["participant_uid"] == str(owner.unique_id)
    assert claims["oan_app"] == created["app"]["app_id"]
    assert claims["oan_environments"] == ["uat"]
    # the routes the app's products cover, read from the gateway
    assert sorted(claims["oan_routes"]) == ["r-search", "r-summary"]
    assert created["app"]["gateway_status"] == "SYNCED"
    # the routes check the token: no consumer, no credential, nothing written to the gateway
    assert writes == [] and fake.consumers == {}


def test_revoked_key_and_deleted_app_lose_their_clients(
    client, admin_headers, participant_headers, farmer_endpoints, kc, monkeypatch
):
    writes = read_only(FakeGateway(_routes()).install(monkeypatch), monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Rotate", [read], admin_headers)
    uid, first = created["app"]["app_id"], created["credential"]
    second = client.post(f"/oan/participant/apps/{uid}/credentials", headers=participant_headers).json()["data"]
    assert set(kc.clients) == {first["api_key"], second["api_key"]}

    client.delete(f"/oan/participant/apps/{uid}/credentials/{first['credential_id']}", headers=participant_headers)
    assert set(kc.clients) == {second["api_key"]}

    assert client.delete(f"/oan/participant/apps/{uid}", headers=participant_headers).status_code == 200
    assert kc.clients == {}
    assert writes == []  # revoking and deleting touch Keycloak only


def test_get_token_returns_the_apps_client_credentials_token(
    client, admin_headers, participant_headers, farmer_endpoints, kc, monkeypatch
):
    FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Console", [read], admin_headers)
    key, secret = created["credential"]["api_key"], created["credential"]["api_secret"]

    auth = client.get("/oan/participant/gateway-auth", headers=participant_headers).json()["data"]
    assert auth["mode"] == "oauth" and auth["token_header"] == HEADER
    assert auth["token_url"].endswith("/protocol/openid-connect/token")
    assert auth["grant_type"] == "client_credentials"

    response = client.post(f"/oan/participant/apps/{created['app']['app_id']}/token", headers=participant_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert kc.tokens_issued == [key]  # client credentials with the app's key + secret
    assert data["client_id"] == key and data["grant_type"] == "client_credentials"
    assert data["header"] == HEADER and data["expires_in"] == 300 and data["expires_at"]
    assert data["token_url"] == auth["token_url"]
    assert data["claims"]["oan_app"] == created["app"]["app_id"]
    assert data["claims"]["oan_environments"] == ["uat"] and data["claims"]["azp"] == key
    assert secret not in response.text  # the secret never leaves the server


def test_get_token_is_only_for_own_active_apps_in_oauth_mode(
    client, admin_headers, participant_headers, farmer_endpoints, kc, monkeypatch
):
    FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Mine", [read], admin_headers)
    url = f"/oan/participant/apps/{created['app']['app_id']}/token"

    assert client.post("/oan/participant/apps/00000000-0000-0000-0000-000000000000/token",
                       headers=participant_headers).status_code == 404
    assert client.post(url).status_code in (401, 403)  # signed-in participants only
    monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "apikey")
    assert client.post(url, headers=participant_headers).status_code == 400
    assert kc.tokens_issued == []


def test_try_it_sends_the_token_in_the_form_never_the_key(
    client, admin_headers, participant_headers, farmer_endpoints, kc, monkeypatch
):
    from app.services import sandbox_service

    FakeGateway(_routes()).install(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.test:9080")
    calls = []
    monkeypatch.setattr(sandbox_service, "_call_upstream",
                        lambda method, url, headers, body: calls.append(headers) or (200, {}, {"ok": True}, None))
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Console", [read], admin_headers)
    uid = created["app"]["app_id"]
    token = client.post(f"/oan/participant/apps/{uid}/token", headers=participant_headers).json()["data"]

    for headers in ({"apikey": "typed", HEADER: token["access_token"]}, {"apikey": "typed"}):
        response = client.post("/oan/participant/try-it", headers=participant_headers, json={
            "endpoint_id": farmer_endpoints[0], "app_id": uid, "body": {}, "headers": headers})
        assert response.status_code == 200, response.text

    with_token, without_token = calls
    assert with_token[HEADER] == token["access_token"]
    assert "apikey" not in {k.lower() for k in with_token}
    # no token in the form: none is fetched behind the partner's back (the gateway answers 401)
    assert HEADER not in without_token and "apikey" not in {k.lower() for k in without_token}
    assert kc.tokens_issued == [created["credential"]["api_key"]]  # only "Get token"


def test_code_sample_shows_the_token_header_and_no_key(
    client, admin_headers, participant_headers, farmer_endpoints, kc, monkeypatch
):
    FakeGateway(_routes()).install(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.test:9080")
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Postman", [read], admin_headers)

    response = client.post("/oan/participant/code-sample", headers=participant_headers, json={
        "endpoint_id": farmer_endpoints[1], "language": "curl",
        "request": {"app_id": created["app"]["app_id"], "headers": {"X-CSRF-Token": "abc"}, "body": {}}})

    code = response.json()["data"]["code"]
    # Only this API's request: the token request is the try-it page's own "App token" snippet.
    assert f"{HEADER}: <app access token>" in code
    assert "openid-connect/token" not in code and "client_secret" not in code
    assert "apikey" not in code and created["credential"]["api_key"] not in code

    # The token "Get token" put in the form goes into the snippet as-is.
    response = client.post("/oan/participant/code-sample", headers=participant_headers, json={
        "endpoint_id": farmer_endpoints[1], "language": "curl",
        "request": {"app_id": created["app"]["app_id"], "headers": {HEADER: "eyJ.fetched.token"}, "body": {}}})
    assert f"{HEADER}: eyJ.fetched.token" in response.json()["data"]["code"]


def test_php_sample_sends_the_headers():
    code = schema_tools.build_code_sample("php", "POST", "http://gw/x", {HEADER: "t", "X-CSRF-Token": "c"}, {"a": 1})
    assert f'CURLOPT_HTTPHEADER, ["{HEADER}: t", "X-CSRF-Token: c"]' in code


def test_oauth_mode_needs_keycloak_and_app_sync():
    with pytest.raises(ValueError, match="GATEWAY_PARTNER_AUTH=oauth needs"):
        type(settings)(GATEWAY_PARTNER_AUTH="oauth", KEYCLOAK_PROVISIONING_ENABLED=False)
