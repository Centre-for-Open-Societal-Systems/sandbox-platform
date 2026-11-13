"""Per-app gateway features: rate limits, IP whitelist and the logs callback."""

# Fixtures imported from test_apps are re-declared as test arguments.
# ruff: noqa: F811

from __future__ import annotations

from app.config.settings import settings
from app.models.app import ParticipantApp
from app.models.catalog import Endpoint, Product
from app.models.logs import ApiLog
from app.services import app_gateway_service
from tests.test_apps import (  # noqa: F401 - farmer_endpoints is a fixture
    FARMER_PATHS,
    FakeGateway,
    _approve_app,
    _create_app,
    _routes,
    farmer_endpoints,
)

LOG_TOKEN = "test-log-token"


def _product(client, admin_headers, name, endpoint_ids, per_minute=None, per_day=None) -> int:
    response = client.post(
        "/oan/admin/api-products",
        headers=admin_headers,
        json={
            "name": name,
            "display_name": name,
            "approval_type": "AUTO",
            "is_published": True,
            "endpoint_ids": endpoint_ids,
            "rate_limit_per_minute": per_minute,
            "quota_per_day": per_day,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["api_product_id"]


def _plugins(fake: FakeGateway, app: dict) -> dict:
    return fake.consumers[app["gateway_consumer"]]["plugins"]


# ------------------------------------------------------------- rate limits
def test_rate_limits_are_off_unless_enabled(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], per_minute=60, per_day=5000)

    app = _create_app(client, participant_headers, "No Limits", [read], admin_headers)["app"]

    assert "limit-count" not in _plugins(fake, app)
    assert app["rate_limit_per_minute"] is None


def test_app_gets_the_most_generous_limits_of_its_products(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_RATE_LIMIT_ENABLED", True)
    small = _product(client, admin_headers, "farmer-small", farmer_endpoints[:1], per_minute=10, per_day=100)
    large = _product(client, admin_headers, "farmer-large", farmer_endpoints[1:2], per_minute=60)

    app = _create_app(client, participant_headers, "Limited", [small], admin_headers)["app"]
    limit = _plugins(fake, app)["limit-count"]
    assert limit["rejected_code"] == 429
    assert limit["policy"] == "local"
    assert [(r["count"], r["time_window"]) for r in limit["rules"]] == [(10, 60), (100, 86400)]
    assert app["rate_limit_per_minute"] == 10 and app["quota_per_day"] == 100

    # A second product: the higher minute limit wins, and having no day
    # quota on it lifts the day quota.
    response = client.post(
        f"/oan/participant/apps/{app['app_id']}/products",
        headers=participant_headers,
        json={"api_product_ids": [large]},
    )
    assert response.status_code == 200, response.text
    rules = _plugins(fake, app)["limit-count"]["rules"]
    assert [(r["count"], r["time_window"]) for r in rules] == [(60, 60)]


def test_changing_a_product_limit_updates_its_apps(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_RATE_LIMIT_ENABLED", True)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], per_minute=10)
    app = _create_app(client, participant_headers, "Updated", [read], admin_headers)["app"]

    response = client.put(
        f"/oan/admin/api-products/{read}",
        headers=admin_headers,
        json={
            "name": "farmer-read",
            "display_name": "farmer-read",
            "approval_type": "AUTO",
            "is_published": True,
            "endpoint_ids": farmer_endpoints[:2],
            "rate_limit_per_minute": 25,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["rate_limit_per_minute"] == 25
    assert _plugins(fake, app)["limit-count"]["rules"][0]["count"] == 25


def test_redis_policy_shares_counts_between_gateway_nodes(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_RATE_LIMIT_POLICY", "redis")
    monkeypatch.setattr(settings, "GATEWAY_RATE_LIMIT_REDIS_HOST", "redis")
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2], per_day=1000)

    app = _create_app(client, participant_headers, "Shared", [read], admin_headers)["app"]

    limit = _plugins(fake, app)["limit-count"]
    assert (limit["policy"], limit["redis_host"], limit["redis_port"]) == ("redis", "redis", 6379)


# ------------------------------------------------------------ IP whitelist
def test_ip_whitelist_is_validated_normalised_and_synced(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])

    bad = client.post(
        "/oan/participant/apps",
        headers=participant_headers,
        json={"name": "Bad IPs", "api_product_ids": [read], "allowed_ips": ["999.1.1.1"]},
    )
    assert bad.status_code == 400

    submitted = client.post(
        "/oan/participant/apps",
        headers=participant_headers,
        json={
            "name": "Server App",
            "api_product_ids": [read],
            "allowed_ips": ["203.0.113.10", " 198.51.100.7/24 ", "203.0.113.10"],
        },
    ).json()["data"]["app"]
    assert submitted["allowed_ips"] == ["203.0.113.10", "198.51.100.0/24"]
    created = _approve_app(client, admin_headers, participant_headers, submitted["app_id"])["app"]
    assert _plugins(fake, created)["ip-restriction"]["whitelist"] == ["203.0.113.10", "198.51.100.0/24"]

    cleared = client.put(
        f"/oan/participant/apps/{created['app_id']}",
        headers=participant_headers,
        json={"allowed_ips": []},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["data"]["allowed_ips"] == []
    assert "ip-restriction" not in _plugins(fake, created)


# ---------------------------------------------------------- logs callback
def test_logger_is_added_only_when_log_ingest_is_configured(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    fake = FakeGateway(_routes()).install(monkeypatch)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    monkeypatch.setattr(settings, "GATEWAY_LOG_INGEST_ENABLED", True)

    missing = _create_app(client, participant_headers, "No Token", [read], admin_headers)["app"]
    assert "http-logger" not in _plugins(fake, missing)
    assert any("GATEWAY_LOG_INGEST_TOKEN" in w for w in missing["gateway_warnings"])

    monkeypatch.setattr(settings, "GATEWAY_LOG_INGEST_URL", "http://sandbox.test/oan/internal/gateway/logs")
    monkeypatch.setattr(settings, "GATEWAY_LOG_INGEST_TOKEN", LOG_TOKEN)
    app = _create_app(client, participant_headers, "Logged", [read], admin_headers)["app"]
    plugin = _plugins(fake, app)["http-logger"]
    assert plugin["uri"] == "http://sandbox.test/oan/internal/gateway/logs"
    assert plugin["auth_header"] == f"Bearer {LOG_TOKEN}"
    # No credential header is ever sent to the callback.
    sent = " ".join(plugin["log_format"].values()).lower()
    assert "apikey" not in sent and "authorization" not in sent


def _enable_ingest(monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_LOG_INGEST_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_LOG_INGEST_TOKEN", LOG_TOKEN)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.internal:9080")
    monkeypatch.setattr(settings, "GATEWAY_UAT_PUBLIC_URL", "https://api.example.org")


def _record(consumer, request_id, uri, **extra) -> dict:
    return {
        "request_id": request_id,
        "time": "2026-10-23T08:26:33+00:00",
        "consumer": consumer,
        "route_id": "r-summary",
        "method": "POST",
        "uri": uri,
        "status": 200,
        "request_time": 0.042,
        "upstream_time": "0.030",
        "client_ip": "203.0.113.10",
        "request_length": 120,
        "bytes_sent": 700,
        "user_agent": "partner-backend/1.0",
        **extra,
    }


def test_logs_callback_is_hidden_when_off_and_needs_the_token(client, monkeypatch):
    assert client.post("/oan/internal/gateway/logs", json=[]).status_code == 404

    _enable_ingest(monkeypatch)
    assert client.post("/oan/internal/gateway/logs", json=[]).status_code == 401
    wrong = client.post("/oan/internal/gateway/logs", json=[], headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


def test_direct_calls_are_stored_once_and_shown_in_api_history(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    leads = Product(product_name="Leads", is_published=True, is_gateway_published=True, country_code="ET")
    db_session.add(leads)
    db_session.flush()
    lead = Endpoint(product_id=leads.product_id, method="GET", endpoint_url="/v1/leads/{id}",
                    display_name="Lead", is_published=True, country_code="ET")
    db_session.add(lead)
    db_session.commit()

    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    _create_app(client, participant_headers, "Partner Backend", [read], admin_headers)
    consumer = app_gateway_service.consumer_name(db_session.query(ParticipantApp).one())
    _enable_ingest(monkeypatch)
    batch = [
        _record(consumer, "req-1", FARMER_PATHS[0]),
        _record(consumer, "req-2", "/v1/leads/L-77", method="GET", status=429, query="page=2"),
        _record(consumer, "req-3", FARMER_PATHS[0], sandbox_txn="TXN-1"),  # try-it: already logged
        _record("some_other_consumer", "req-4", FARMER_PATHS[0]),
        _record("oanapp_unknown", "req-5", FARMER_PATHS[0]),
    ]
    headers = {"Authorization": f"Bearer {LOG_TOKEN}"}

    first = client.post("/oan/internal/gateway/logs", json=batch, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"] == {"stored": 2, "skipped": 3}
    again = client.post("/oan/internal/gateway/logs", json=batch[:2], headers=headers)
    assert again.json()["data"] == {"stored": 0, "skipped": 2}

    rows = {row.gateway_request_id: row for row in db_session.query(ApiLog).all()}
    assert set(rows) == {"req-1", "req-2"}
    summary = rows["req-1"]
    assert summary.source == "DIRECT"
    assert summary.endpoint_id == farmer_endpoints[0]
    assert summary.latency_ms == 42.0 and summary.upstream_latency_ms == 30.0
    assert summary.target_url == f"https://api.example.org{FARMER_PATHS[0]}"
    assert summary.request_headers == {"User-Agent": "partner-backend/1.0"}
    templated = rows["req-2"]
    assert (templated.endpoint_id, templated.endpoint_url) == (lead.endpoint_id, "/v1/leads/{id}")
    assert templated.target_url.endswith("/v1/leads/L-77?page=2")
    assert templated.error_message == "Rate limit exceeded."

    history = client.post(
        "/oan/participant/api-history", headers=participant_headers, json={"source": "DIRECT"}
    ).json()["data"]["logs"]
    assert {row["transaction_id"] for row in history} == {"req-1", "req-2"}
    assert {row["app_name"] for row in history} == {"Partner Backend"}


def test_calls_reported_by_the_routes_are_stored_for_the_app_they_name(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    """App OAuth tokens: no consumer, the route's http-logger names the app (X-OAN-App)."""
    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    app = _create_app(client, participant_headers, "Token Backend", [read], admin_headers)["app"]
    _enable_ingest(monkeypatch)
    batch = [
        _record("", "req-1", FARMER_PATHS[0], app=app["app_id"]),
        _record("", "req-2", FARMER_PATHS[0], app=app["app_id"].upper(), status=403),
        _record("", "req-3", FARMER_PATHS[0], app=app["app_id"], sandbox_txn="TXN-1"),  # try-it
        _record("", "req-4", FARMER_PATHS[0]),  # refused before the token named an app
        _record("", "req-5", FARMER_PATHS[0], app="00000000-0000-0000-0000-000000000000"),
        _record("", "req-6", FARMER_PATHS[0], app="not-an-id"),
    ]
    headers = {"Authorization": f"Bearer {LOG_TOKEN}"}

    first = client.post("/oan/internal/gateway/logs", json=batch, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["data"] == {"stored": 2, "skipped": 4}
    again = client.post("/oan/internal/gateway/logs", json=batch[:2], headers=headers)
    assert again.json()["data"] == {"stored": 0, "skipped": 2}

    rows = {row.gateway_request_id: row for row in db_session.query(ApiLog).all()}
    assert set(rows) == {"req-1", "req-2"}
    assert rows["req-1"].source == "DIRECT"
    assert rows["req-1"].endpoint_id == farmer_endpoints[0]
    assert rows["req-2"].error_message.startswith("Rejected: no access")
    history = client.post(
        "/oan/participant/api-history", headers=participant_headers, json={"source": "DIRECT"}
    ).json()["data"]["logs"]
    assert {row["app_name"] for row in history} == {"Token Backend"}


def test_try_it_rows_are_marked_with_their_source_and_app(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    from app.services import sandbox_service

    monkeypatch.setattr(settings, "GATEWAY_APP_SYNC_ENABLED", False)
    monkeypatch.setattr(settings, "GATEWAY_ENABLED", True)
    monkeypatch.setattr(settings, "GATEWAY_UAT_URL", "http://apisix.test:9080")
    monkeypatch.setattr(sandbox_service, "_call_upstream", lambda *a: (200, {}, {"ok": True}, None))
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Console", [read], admin_headers)

    client.post(
        "/oan/participant/try-it",
        headers=participant_headers,
        json={"endpoint_id": farmer_endpoints[0], "app_id": created["app"]["app_id"], "body": {}},
    )

    row = db_session.query(ApiLog).one()
    assert row.source == "TRYIT"
    assert row.app_id is not None


def test_product_can_be_deleted_once_its_apps_are_deleted(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    FakeGateway(_routes()).install(monkeypatch)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    app = _create_app(client, participant_headers, "Short Lived", [read], admin_headers)["app"]

    blocked = client.delete(f"/oan/admin/api-products/{read}", headers=admin_headers)
    assert blocked.status_code == 409
    client.delete(f"/oan/participant/apps/{app['app_id']}", headers=participant_headers)
    assert client.delete(f"/oan/admin/api-products/{read}", headers=admin_headers).status_code == 200


def test_a_deleted_apps_name_can_be_used_again(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    FakeGateway(_routes()).install(monkeypatch)
    read = _product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    first = _create_app(client, participant_headers, "Reused Name", [read], admin_headers)["app"]
    client.delete(f"/oan/participant/apps/{first['app_id']}", headers=participant_headers)

    again = _create_app(client, participant_headers, "Reused Name", [read], admin_headers)["app"]
    assert again["app_id"] != first["app_id"]
