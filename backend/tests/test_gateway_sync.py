"""Pull from the API gateway: Admin API readers and the catalogue sync."""

from __future__ import annotations

import httpx
import pytest

from app.integrations import gateway
from app.integrations.gateway import GatewayRoute, GatewayService, GatewaySnapshot

SPEC = """
openapi: 3.0.3
info: {title: Leads, version: "1.0"}
paths:
  /v1/leads/{leadId}:
    get:
      summary: Get a lead
      parameters:
        - {name: leadId, in: path, required: true, schema: {type: string}}
      responses:
        "200": {description: ok}
"""


# ------------------------------------------------------------ translators
@pytest.mark.parametrize(
    ("uri", "path"),
    [
        ("/v1/me", "/v1/me"),
        ("/v1/leads/:id/status", "/v1/leads/{id}/status"),
        ("/v1/admin/users/:user_id/roles/:role", "/v1/admin/users/{user_id}/roles/{role}"),
        ("/socket.io/*", None),
    ],
)
def test_apisix_uri_to_path(uri, path):
    assert gateway.apisix_uri_to_path(uri) == path


@pytest.mark.parametrize(
    ("kong_path", "path"),
    [
        ("/v1/me", "/v1/me"),
        ("~/v1/me$", "/v1/me"),
        ("~/v1/leads/(?<id>[^/]+)/status$", "/v1/leads/{id}/status"),
        ("~/files/.+$", None),
    ],
)
def test_kong_path_to_path(kong_path, path):
    assert gateway.kong_path_to_path(kong_path) == path


# ---------------------------------------------------------------- readers
def _client(routes: dict[str, dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=routes[request.url.path])

    return httpx.Client(base_url="http://gw.test", transport=httpx.MockTransport(handler))


def test_apisix_reader_maps_services_routes_and_auth():
    client = _client(
        {
            "/apisix/admin/services": {
                "total": 1,
                "list": [{"value": {"id": "s1", "name": "a2c-bff-v1", "plugins": {"cors": {}}}}],
            },
            "/apisix/admin/routes": {
                "total": 3,
                "list": [
                    {"value": {"id": "r1", "name": "get-me", "service_id": "s1", "uris": ["/v1/me"],
                               "methods": ["GET"], "plugins": {"jwt-auth": {}}}},
                    {"value": {"id": "r2", "name": "charts", "service_id": "s1",
                               "uri": "/v1/charts/:chart_id", "methods": ["GET"],
                               "plugins": {"key-auth": {"header": "apikey"}}}},
                    {"value": {"id": "r3", "name": "grievances", "uris": ["/v1/grievances", "/socket.io/*"],
                               "methods": ["GET", "OPTIONS"], "labels": {"auth": "bearer"}}},
                ],
            },
        }
    )
    snapshot = gateway._read_apisix(client)

    assert [s.key for s in snapshot.services] == ["apisix:s1"]
    me, charts, grievances = snapshot.routes
    assert (me.service_key, me.paths, me.auth_header) == ("apisix:s1", ["/v1/me"], "Authorization")
    assert (charts.paths, charts.auth_header) == (["/v1/charts/{chart_id}"], "apikey")
    assert grievances.service_key is None
    assert grievances.paths == ["/v1/grievances"] and grievances.skipped == ["/socket.io/*"]
    assert grievances.auth_header == "Authorization"  # from the auth: bearer label


def test_kong_reader_resolves_route_and_service_plugins():
    client = _client(
        {
            "/services": {"data": [{"id": "s1", "name": "a2c-bff-v1"}], "next": None},
            "/plugins": {
                "data": [
                    {"name": "cors", "service": {"id": "s1"}, "route": None, "enabled": True},
                    {"name": "jwt", "route": {"id": "r1"}, "enabled": True},
                ],
                "next": None,
            },
            "/routes": {
                "data": [
                    {"id": "r1", "name": "get-lead", "service": {"id": "s1"},
                     "paths": ["~/v1/leads/(?<id>[^/]+)$"], "methods": ["GET"]},
                ],
                "next": None,
            },
        }
    )
    snapshot = gateway._read_kong(client)

    (route,) = snapshot.routes
    assert route.service_key == "kong:s1"
    assert route.paths == ["/v1/leads/{id}"]
    assert route.auth_header == "Authorization"


def test_fetch_refuses_when_sync_is_disabled(monkeypatch):
    from app.config.settings import settings
    from app.core.exceptions import ValidationError

    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", False)
    with pytest.raises(ValidationError):
        gateway.fetch()


# ------------------------------------------------------------------ sync
def _fake_gateway(monkeypatch, routes: list[GatewayRoute]):
    from app.config.settings import settings
    from app.services import gateway_sync_service

    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_ADMIN_URL", "http://gw.test")
    snapshot = GatewaySnapshot(
        gateway_type="apisix",
        services=[GatewayService(key="apisix:s1", name="a2c-bff-v1", description="A2C")],
        routes=routes,
    )
    monkeypatch.setattr(gateway_sync_service.gateway, "fetch", lambda: snapshot)


def _sync(client, admin_headers, dry_run=False) -> dict:
    response = client.post("/oan/admin/gateway/sync", headers=admin_headers, json={"dry_run": dry_run})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_status_reports_the_configuration(client, admin_headers, monkeypatch):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_TYPE", "kong")
    monkeypatch.setattr(settings, "GATEWAY_ADMIN_URL", "")
    data = client.get("/oan/admin/gateway/status", headers=admin_headers).json()["data"]
    assert data == {"enabled": True, "gateway_type": "kong", "admin_url_configured": False,
                    "environments": ["UAT"]}


def test_sync_is_refused_when_disabled(client, admin_headers, monkeypatch):
    from app.config.settings import settings

    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", False)
    response = client.post("/oan/admin/gateway/sync", headers=admin_headers, json={})
    assert response.status_code == 400


def test_sync_creates_a_product_and_endpoints_then_is_idempotent(client, admin_headers, monkeypatch):
    _fake_gateway(
        monkeypatch,
        [
            GatewayRoute(name="get-me", service_key="apisix:s1", paths=["/v1/me"], methods=["GET"],
                         auth_header="Authorization", auth_hint="Bearer <access token>"),
            GatewayRoute(name="lead", service_key="apisix:s1", paths=["/v1/leads/{id}"],
                         methods=["GET", "PATCH", "OPTIONS"]),
            GatewayRoute(name="files", service_key="apisix:s1", paths=[], methods=["GET"],
                         skipped=["/files/*"]),
        ],
    )

    first = _sync(client, admin_headers)
    assert first["created_count"] == 3 and first["updated_count"] == 0
    assert [p["product_name"] for p in first["products_created"]] == ["a2c-bff-v1"]
    assert first["skipped_count"] == 1

    product_id = first["products_created"][0]["product_id"]
    product = client.get(f"/oan/admin/products/{product_id}", headers=admin_headers).json()["data"]
    assert product["is_gateway_published"] is True and product["is_published"] is False
    endpoints = {(e["method"], e["endpoint_url"]): e for e in product["endpoints"]}
    me = client.get(
        f"/oan/admin/endpoints/{endpoints[('GET', '/v1/me')]['endpoint_id']}", headers=admin_headers
    ).json()["data"]
    assert me["header_params"]["Authorization"]["required"] is True
    lead = client.get(
        f"/oan/admin/endpoints/{endpoints[('PATCH', '/v1/leads/{id}')]['endpoint_id']}",
        headers=admin_headers,
    ).json()["data"]
    assert "id" in lead["path_params"]

    second = _sync(client, admin_headers)
    assert (second["created_count"], second["updated_count"], second["unchanged"]) == (0, 0, 3)
    assert second["products_created"] == []


def test_sync_updates_an_imported_endpoint_without_overwriting_it(client, admin_headers, monkeypatch):
    created = client.post(
        "/oan/admin/products", headers=admin_headers,
        json={"product_name": "leads", "is_gateway_published": True},
    ).json()["data"]
    client.post(
        "/oan/admin/products/import-spec", headers=admin_headers,
        json={"product_id": created["product_id"], "spec_text": SPEC},
    )
    _fake_gateway(
        monkeypatch,
        [GatewayRoute(name="lead", service_key="apisix:s1", paths=["/v1/leads/{id}"], methods=["GET"],
                      auth_header="apikey", auth_hint="<API key>")],
    )

    report = _sync(client, admin_headers)
    assert report["created_count"] == 0
    (row,) = report["updated"]
    assert row["product_id"] == created["product_id"]
    assert row["changes"] == ["apikey header"]

    endpoint = client.get(f"/oan/admin/endpoints/{row['endpoint_id']}", headers=admin_headers).json()["data"]
    assert endpoint["display_name"] == "Get a lead"  # from the spec, kept
    assert "leadId" in endpoint["path_params"] and "id" not in endpoint["path_params"]
    assert endpoint["header_params"]["apikey"]["required"] is True


def test_a_new_route_joins_the_product_already_holding_its_service(client, admin_headers, monkeypatch):
    # Products loaded before the sync (no gateway_product_id), split by domain like A2C.
    for name, spec in (("leads", SPEC), ("other", SPEC.replace("/v1/leads/", "/v1/banks/"))):
        created = client.post(
            "/oan/admin/products", headers=admin_headers,
            json={"product_name": name, "is_gateway_published": True},
        ).json()["data"]
        client.post(
            "/oan/admin/products/import-spec", headers=admin_headers,
            json={"product_id": created["product_id"], "spec_text": spec},
        )
        if name == "leads":
            leads_id = created["product_id"]
    _fake_gateway(
        monkeypatch,
        [
            GatewayRoute(name="lead", service_key="apisix:s1", paths=["/v1/leads/{id}"], methods=["GET"]),
            GatewayRoute(name="bank", service_key="apisix:s1", paths=["/v1/banks/{id}"], methods=["GET"]),
            GatewayRoute(name="new", service_key="apisix:s1", paths=["/v1/leads/{id}/notes"], methods=["POST"]),
        ],
    )

    preview = _sync(client, admin_headers, dry_run=True)
    assert preview["products_created"] == []
    assert [(r["method"], r["path"], r["product_id"]) for r in preview["created"]] == [
        ("POST", "/v1/leads/{id}/notes", leads_id)
    ]


def test_dry_run_reports_without_saving_and_missing_routes_are_listed(client, admin_headers, monkeypatch):
    created = client.post(
        "/oan/admin/products", headers=admin_headers,
        json={"product_name": "leads", "is_gateway_published": True},
    ).json()["data"]
    client.post(
        "/oan/admin/products/import-spec", headers=admin_headers,
        json={"product_id": created["product_id"], "spec_text": SPEC},
    )
    _fake_gateway(
        monkeypatch,
        [GatewayRoute(name="get-me", service_key="apisix:s1", paths=["/v1/me"], methods=["GET"])],
    )

    preview = _sync(client, admin_headers, dry_run=True)
    assert preview["dry_run"] is True
    assert preview["created_count"] == 1 and preview["created"][0]["product_id"] is None
    assert [(m["method"], m["path"]) for m in preview["missing"]] == [("GET", "/v1/leads/{leadId}")]

    products = client.post(
        "/oan/admin/products/list", headers=admin_headers, json={"page": 1, "limit": 50}
    ).json()["data"]["products"]
    assert [p["product_name"] for p in products] == ["leads"]


def test_routes_with_a_user_token_and_an_app_key_need_both_headers():
    from app.services.gateway_sync_service import _auth_params

    route = GatewayRoute(
        name="get-me", service_key="apisix:s1", paths=["/v1/me"], methods=["GET"],
        auth_header="Authorization", auth_hint="Bearer <access token>", key_header="apikey",
    )
    params = _auth_params(route, {})
    assert set(params) == {"Authorization", "apikey"}
    assert all(p["required"] for p in params.values())
    # A route checking only the app key gets it once.
    only_key = GatewayRoute(name="login", service_key=None, paths=["/v1/auth/login"], methods=["POST"],
                            auth_header="apikey", auth_hint="<API key>", key_header="apikey")
    assert list(_auth_params(only_key, {})) == ["apikey"]


def test_apisix_reader_reports_the_app_key_header():
    client = _client({
        "/apisix/admin/services": {"total": 0, "list": []},
        "/apisix/admin/routes": {"total": 1, "list": [{"value": {
            "id": "r1", "name": "me", "uri": "/v1/me", "methods": ["GET"],
            "plugins": {"jwt-auth": {}, "key-auth": {"header": "apikey"}}}}]},
    })
    route = gateway._read_apisix(client).routes[0]
    assert (route.id, route.auth_header, route.key_header) == ("r1", "Authorization", "apikey")
