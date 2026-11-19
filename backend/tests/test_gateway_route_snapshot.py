"""After a pull the sandbox keeps the gateway's routes (GatewayRouteSnapshot): app sync
resolves route ids from that copy, so approving apps needs nothing from the Admin API;
a pull re-syncs the apps whose route ids changed; ``auto_pull`` runs it on its own."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config.settings import settings
from app.core.exceptions import UpstreamError
from app.integrations.gateway import GatewayRoute, GatewaySnapshot
from app.models.app import GatewayRouteSnapshot
from app.models.catalog import Endpoint
from app.models.logs import UserActionLog
from app.services import gateway_sync_service
from tests import test_apps
from tests.test_apps import (
    FARMER_PATHS,
    FakeGateway,
    _api_product,
    _create_app,
    _routes,
)
from tests.test_gateway_oauth_apps import FakeKeycloakClients

farmer_endpoints = test_apps.farmer_endpoints  # fixture
NEW_PATH = "/farmer-registry/register-data/get_register_list"


@pytest.fixture
def kc(monkeypatch):
    return FakeKeycloakClients().install(monkeypatch)


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGateway(_routes()).install(monkeypatch)
    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", True)
    monkeypatch.setattr(
        gateway_sync_service.gateway,
        "fetch",
        lambda: GatewaySnapshot(gateway_type="apisix", services=[], routes=list(fake.routes)),
    )
    return fake


def _gateway_down(monkeypatch):
    def down():
        raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL.")

    monkeypatch.setattr(test_apps.gateway, "list_routes", down)


def _pull(client, admin_headers) -> dict:
    response = client.post("/oan/admin/gateway/sync", headers=admin_headers, json={})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_after_a_pull_apps_are_approved_without_the_admin_api(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, kc, fake, monkeypatch
):
    _pull(client, admin_headers)
    snapshot = db_session.get(GatewayRouteSnapshot, "UAT")
    assert {r["id"] for r in snapshot.routes} == {"r-summary", "r-search", "r-mixed"}
    _gateway_down(monkeypatch)

    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)

    assert created["app"]["gateway_status"] == "SYNCED"
    assert sorted(kc.clients[created["credential"]["api_key"]]["claims"]["oan_routes"]) == ["r-search", "r-summary"]


def test_never_pulled_gateway_is_read_live(
    client, admin_headers, participant_headers, farmer_endpoints, kc, fake, monkeypatch
):
    _gateway_down(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    assert created["app"]["gateway_status"] == "FAILED"


def test_a_pull_resyncs_apps_whose_route_ids_changed(
    client, admin_headers, participant_headers, farmer_endpoints, kc, fake
):
    _pull(client, admin_headers)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Server App", [read], admin_headers)
    key = created["credential"]["api_key"]

    # The Helm chart renamed a route: same path, new id.
    fake.routes[0] = GatewayRoute(id="r-summary-v2", name="summary-v2", service_key=None,
                                  paths=[FARMER_PATHS[0]], methods=["POST"])
    report = _pull(client, admin_headers)
    assert report["apps_resynced"] == 1
    assert sorted(kc.clients[key]["claims"]["oan_routes"]) == ["r-search", "r-summary-v2"]

    assert _pull(client, admin_headers)["apps_resynced"] == 0


def test_auto_pull_adds_new_routes_unpublished_and_waits_for_its_interval(
    farmer_endpoints, db_session, fake, monkeypatch
):
    monkeypatch.setattr(settings, "GATEWAY_AUTO_PULL_HOURS", 24)
    fake.routes.append(GatewayRoute(id="r-list", name="list", service_key=None, paths=[NEW_PATH], methods=["POST"]))

    summaries = gateway_sync_service.auto_pull(db_session)

    assert summaries == [{"environment": "UAT", "created": 1, "updated": 0, "missing": 0, "apps_resynced": 0}]
    new = db_session.query(Endpoint).filter_by(endpoint_url=NEW_PATH).one()
    assert new.is_published is False and new.added_by is None
    assert db_session.get(GatewayRouteSnapshot, "UAT").pulled_by == "automatic"
    audit = db_session.query(UserActionLog).filter_by(action="GATEWAY_SYNC").one()
    assert audit.actor_name == "automatic" and audit.description.startswith("Automatic pull")

    # pulled less than a day ago (by hand or by another replica): nothing to do
    assert gateway_sync_service.auto_pull(db_session) == []
    snapshot = db_session.get(GatewayRouteSnapshot, "UAT")
    snapshot.pulled_date = datetime.now(UTC) - timedelta(hours=25)
    db_session.commit()
    assert gateway_sync_service.auto_pull(db_session)[0]["created"] == 0


def test_auto_pull_is_off_with_zero_hours_or_without_pulling(db_session, fake, monkeypatch):
    monkeypatch.setattr(settings, "GATEWAY_AUTO_PULL_HOURS", 0)
    assert gateway_sync_service.auto_pull(db_session) == []
    monkeypatch.setattr(settings, "GATEWAY_AUTO_PULL_HOURS", 24)
    monkeypatch.setattr(settings, "GATEWAY_SYNC_ENABLED", False)
    assert gateway_sync_service.auto_pull(db_session) == []
    assert db_session.get(GatewayRouteSnapshot, "UAT") is None


def test_auto_pull_reports_a_gateway_that_fails(db_session, fake, monkeypatch):
    def down():
        raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL.")

    monkeypatch.setattr(gateway_sync_service.gateway, "fetch", down)
    assert gateway_sync_service.auto_pull(db_session) == [
        {"environment": "UAT", "error": "The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL."}
    ]
