"""OAuth scopes (GATEWAY_SCOPES): the gateway's Helm chart says which scope each route
needs; an app's token carries the scopes of its approved API products in ``scope`` and
the audience in ``aud``. With the legacy route claim off, app sync reads nothing from
the gateway. Production clients can use private_key_jwt with the partner's key."""

from __future__ import annotations

import json

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config.settings import Settings, settings
from app.core.exceptions import UpstreamError
from app.models.app import ParticipantApp
from app.services import gateway_scope_service
from tests import test_apps
from tests.test_apps import FakeGateway, _api_product, _create_app, _routes
from tests.test_gateway_oauth_apps import FakeKeycloakClients
from tests.test_production_environment import production_app, set_production_access

farmer_endpoints = test_apps.farmer_endpoints  # fixture

SCOPES = {
    "/farmer-registry/register-data": "oan:farmer-read",
    "POST /farmer-registry/intake-form-data/save_intake_form_submission": "oan:farmer-write",
}


@pytest.fixture
def kc(monkeypatch):
    return FakeKeycloakClients().install(monkeypatch)


@pytest.fixture
def scoped(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_SCOPES", json.dumps(SCOPES))
    return FakeGateway(_routes()).install(monkeypatch)


def _gateway_down(monkeypatch):
    def down():
        raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL.")

    monkeypatch.setattr(test_apps.gateway, "list_routes", down)


# ------------------------------------------------------------ the scope map
@pytest.mark.parametrize(
    ("method", "path", "scope"),
    [
        ("POST", "/farmer-registry/register-data/search_in_a_register", "oan:farmer-read"),
        ("GET", "/farmer-registry/register-data", "oan:farmer-read"),
        ("POST", "/farmer-registry/intake-form-data/save_intake_form_submission", "oan:farmer-write"),
        ("GET", "/farmer-registry/intake-form-data/save_intake_form_submission", None),  # other method
        ("POST", "/farmer-registry/register-database/x", None),  # a string prefix, not a segment
        ("POST", "/elsewhere", None),
    ],
)
def test_scope_for_matches_operations_then_whole_segments(monkeypatch, method, path, scope):
    monkeypatch.setattr(settings, "GATEWAY_SCOPES", json.dumps(SCOPES))
    assert gateway_scope_service.scope_for(method, path) == scope


def test_longest_prefix_wins(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_SCOPES", json.dumps(
        {"/consent-manager": "oan:consent-manager-portal", "/consent-manager-partner": "oan:consent-manager-partner",
         "/a": "oan:a", "/a/b": "oan:ab"}))
    assert gateway_scope_service.scope_for("POST", "/consent-manager-partner/consent/v1/validate") == \
        "oan:consent-manager-partner"
    assert gateway_scope_service.scope_for("POST", "/consent-manager/consent/v1/partner-portal/x") == \
        "oan:consent-manager-portal"
    assert gateway_scope_service.scope_for("GET", "/a/b/c") == "oan:ab"


@pytest.mark.parametrize(
    "value",
    ['{"/x": "profile"}', '{"/x": "oan:"}', '{"x": "oan:x"}', '["oan:x"]', "{not json", '{"/x": "oan:a b"}'],
)
def test_malformed_or_foreign_scopes_are_refused_at_start_up(value):
    with pytest.raises(ValueError):
        Settings(GATEWAY_SCOPES=value)


# --------------------------------------------------------------- app tokens
def test_token_carries_the_products_scopes_and_the_audience(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, kc, scoped
):
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    client_row = kc.clients[created["credential"]["api_key"]]

    assert client_row["scopes"] == ["oan:farmer-read"]
    assert client_row["audience"] == "oan-partner-gateway"
    # legacy (default): the route ids still travel, for gateways not yet on scopes
    assert sorted(client_row["claims"]["oan_routes"]) == ["r-search", "r-summary"]
    app = db_session.query(ParticipantApp).filter_by(name="Server App").one()
    assert app.gateway_scopes == ["oan:farmer-read"]

    token = client.post(f"/oan/participant/apps/{created['app']['app_id']}/token", headers=participant_headers)
    assert token.status_code == 200, token.text
    shown = token.json()["data"]["claims"]
    assert shown["scope"] == "oan:farmer-read" and shown["aud"] == "oan-partner-gateway"


def test_scopes_only_needs_nothing_from_the_gateway(
    client, admin_headers, participant_headers, farmer_endpoints, kc, scoped, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_LEGACY_ROUTE_CLAIM", False)
    _gateway_down(monkeypatch)
    write = _api_product(client, admin_headers, "farmer-write", farmer_endpoints[3:4])
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])

    created = _create_app(client, participant_headers, "Server App", [read, write], admin_headers)

    assert created["app"]["gateway_status"] == "SYNCED"
    client_row = kc.clients[created["credential"]["api_key"]]
    assert client_row["scopes"] == ["oan:farmer-read", "oan:farmer-write"]
    assert "oan_routes" not in client_row["claims"]


def test_endpoint_outside_the_scope_map_stays_closed_with_a_warning(
    client, admin_headers, participant_headers, farmer_endpoints, kc, scoped, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_SCOPES", json.dumps({"/farmer-registry/register-data": "oan:farmer-read"}))
    write = _api_product(client, admin_headers, "farmer-write", farmer_endpoints[3:4])
    created = _create_app(client, participant_headers, "Server App", [write], admin_headers)
    assert kc.clients[created["credential"]["api_key"]]["scopes"] == []
    assert any("no gateway scope covers it" in w for w in created["app"]["gateway_warnings"])


def test_product_detail_shows_when_a_scope_opens_more_than_it_lists(
    client, admin_headers, farmer_endpoints, scoped, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_PARTNER_AUTH", "oauth")
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    whole = _api_product(client, admin_headers, "farmer-all-read", farmer_endpoints[:3])

    def scopes(product_id):
        response = client.get(f"/oan/admin/api-products/{product_id}", headers=admin_headers)
        assert response.status_code == 200, response.text
        return response.json()["data"]["gateway_scopes"]

    assert scopes(read) == [{"scope": "oan:farmer-read", "in_product": 2, "total": 3, "whole_api": False}]
    assert scopes(whole) == [{"scope": "oan:farmer-read", "in_product": 3, "total": 3, "whole_api": True}]


def test_resync_all_rewrites_every_active_app(
    client, admin_headers, participant_headers, farmer_endpoints, kc, scoped, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_SCOPES", "")
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    key = created["credential"]["api_key"]
    assert kc.clients[key]["scopes"] == []

    monkeypatch.setattr(settings, "GATEWAY_SCOPES", json.dumps(SCOPES))
    response = client.post("/oan/admin/apps/gateway-sync-all", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"apps": 1, "synced": 1, "failed": 0}
    assert kc.clients[key]["scopes"] == ["oan:farmer-read"]


# --------------------------------------------- production: private_key_jwt
def _pem(key) -> str:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


def test_production_clients_use_the_partners_key_not_the_secret(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, kc, scoped, monkeypatch
):
    monkeypatch.setattr(settings, "KEYCLOAK_PROD_CLIENT_AUTH", "private-key-jwt")
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    uat = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    owner = set_production_access(db_session)
    owner.public_key = _pem(rsa.generate_private_key(public_exponent=65537, key_size=2048))
    db_session.commit()

    prod = production_app(client, admin_headers, participant_headers, uat["app"]["app_id"])

    assert kc.clients[uat["credential"]["api_key"]]["jwks"] is None  # UAT keeps key + secret
    jwks = kc.clients[prod["credential"]["api_key"]]["jwks"]
    assert [k["kty"] for k in jwks["keys"]] == ["RSA"] and jwks["keys"][0]["alg"] == "RS256"
    refused = client.post(f"/oan/participant/apps/{prod['app']['app_id']}/token", headers=participant_headers)
    assert refused.status_code == 400 and "client_assertion" in refused.text


def test_production_client_without_a_partner_key_is_not_written(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, kc, scoped, monkeypatch
):
    monkeypatch.setattr(settings, "KEYCLOAK_PROD_CLIENT_AUTH", "private-key-jwt")
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    uat = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    set_production_access(db_session)  # approved, but no signing key on record

    prod = production_app(client, admin_headers, participant_headers, uat["app"]["app_id"])

    assert prod["app"]["gateway_status"] == "FAILED"
    row = db_session.query(ParticipantApp).filter_by(unique_id=prod["app"]["app_id"]).one()
    assert "private_key_jwt" in row.gateway_error  # the administrator's view; the partner sees a generic note
    assert prod["credential"]["api_key"] not in kc.clients
