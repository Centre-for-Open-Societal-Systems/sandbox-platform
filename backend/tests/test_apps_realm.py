"""KEYCLOAK_APPS_REALM: sandbox apps' OAuth clients live in a realm of their own
(partner-sandbox-app), apart from the partners' users in KEYCLOAK_REALM; copies written
to another realm before are removed; production apps follow unless production has its
own Keycloak (whose realm defaults to the apps realm's name)."""

from __future__ import annotations

import pytest

from app.config.settings import settings
from app.integrations import keycloak
from tests import test_apps
from tests.test_apps import FakeGateway, _api_product, _create_app, _routes
from tests.test_gateway_oauth_apps import FakeKeycloakClients
from tests.test_production_environment import production_app, set_production_access

farmer_endpoints = test_apps.farmer_endpoints  # fixture
APPS = "partner-sandbox-app"


class FakeRealmClients(FakeKeycloakClients):
    """App clients per realm name (keycloak.current_realm())."""

    def __init__(self):
        super().__init__()
        self.by_realm: dict[str, dict[str, dict]] = {}
        self.admin_clients: set[str] = set()
        self.token_urls: list[str] = []

    def install(self, monkeypatch):
        super().install(monkeypatch)
        monkeypatch.setattr(settings, "KEYCLOAK_URL", "http://keycloak:8080")
        monkeypatch.setattr(settings, "KEYCLOAK_PUBLIC_URL", "https://keycloak.example.org")
        monkeypatch.setattr(settings, "KEYCLOAK_REALM", "partner")
        monkeypatch.setattr(settings, "KEYCLOAK_APPS_REALM", APPS)
        monkeypatch.setattr(settings, "KEYCLOAK_APPS_ADMIN_CLIENT_ID", "oan-sandbox-app-provisioner")
        monkeypatch.setattr(settings, "KEYCLOAK_APPS_ADMIN_CLIENT_SECRET", "apps-provisioner-secret")
        return self

    @staticmethod
    def realm() -> str:
        return keycloak.current_realm().name

    def upsert(self, client_id, secret, app_uid, description, claims, scopes=None, audience="", jwks=None):
        super().upsert(client_id, secret, app_uid, description, claims, scopes, audience, jwks)
        self.by_realm.setdefault(self.realm(), {})[client_id] = self.clients[client_id]
        self.admin_clients.add(keycloak.current_realm().admin_client_id)

    def delete(self, client_id):
        self.by_realm.get(self.realm(), {}).pop(client_id, None)

    def token(self, client_id, secret):
        self.token_urls.append(keycloak.token_url(public=False))
        return super().token(client_id, secret)

    def where(self, client_id) -> list[str]:
        return sorted(name for name, clients in self.by_realm.items() if client_id in clients)


@pytest.fixture
def realms(monkeypatch):
    fake = FakeRealmClients().install(monkeypatch)
    monkeypatch.setattr(keycloak, "delete_app_client", fake.delete)
    FakeGateway(_routes()).install(monkeypatch)
    return fake


def test_app_clients_live_in_the_apps_realm_only(
    client, admin_headers, participant_headers, farmer_endpoints, realms
):
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    key = created["credential"]["api_key"]

    assert realms.where(key) == [APPS]
    assert realms.admin_clients == {"oan-sandbox-app-provisioner"}  # the apps realm's own service account
    token = client.post(f"/oan/participant/apps/{created['app']['app_id']}/token", headers=participant_headers)
    assert token.status_code == 200, token.text
    assert realms.token_urls == [f"http://keycloak:8080/realms/{APPS}/protocol/openid-connect/token"]
    assert token.json()["data"]["token_url"] == \
        f"https://keycloak.example.org/realms/{APPS}/protocol/openid-connect/token"


def test_copies_in_the_users_realm_are_removed_on_the_next_sync(
    client, admin_headers, participant_headers, farmer_endpoints, realms, monkeypatch
):
    monkeypatch.setattr(settings, "KEYCLOAK_APPS_REALM", "")  # before the apps realm existed
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    key = created["credential"]["api_key"]
    assert realms.where(key) == ["partner"]

    monkeypatch.setattr(settings, "KEYCLOAK_APPS_REALM", APPS)
    response = client.post("/oan/admin/apps/gateway-sync-all", headers=admin_headers)
    assert response.json()["data"]["synced"] == 1
    assert realms.where(key) == [APPS]


def test_production_apps_use_the_apps_realm_or_productions_own_keycloak(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, realms, monkeypatch
):
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    uat = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    set_production_access(db_session)
    prod = production_app(client, admin_headers, participant_headers, uat["app"]["app_id"])
    key = prod["credential"]["api_key"]
    assert realms.where(key) == [APPS]

    monkeypatch.setattr(settings, "KEYCLOAK_PROD_URL", "http://keycloak.prod:8080")
    monkeypatch.setattr(settings, "KEYCLOAK_PROD_ADMIN_CLIENT_SECRET", "prod-secret")
    assert keycloak.realm_for("PRODUCTION").name == APPS  # production's realm takes the same name
    assert keycloak.realm_for("PRODUCTION").url == "http://keycloak.prod:8080"


def test_no_apps_realm_keeps_app_clients_with_the_users(monkeypatch):
    monkeypatch.setattr(settings, "KEYCLOAK_REALM", "partner")
    for value in ("", "partner"):
        monkeypatch.setattr(settings, "KEYCLOAK_APPS_REALM", value)
        assert keycloak.apps_realm() is None
        assert keycloak.realm_for("UAT").name == "partner"
