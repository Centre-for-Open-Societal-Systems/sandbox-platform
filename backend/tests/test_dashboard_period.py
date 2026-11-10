"""Admin dashboard: today, this week and this month windows."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models.logs import ApiLog
from app.services import log_service

# A Wednesday, so the week starts two days earlier and the month ten days earlier.
NOW = datetime(2026, 11, 11, 15, 30, tzinfo=UTC)


@pytest.fixture
def traffic(db_session, monkeypatch):
    monkeypatch.setattr(log_service, "_now", lambda: NOW)
    calls = [
        (datetime(2026, 11, 11, 9, 5, tzinfo=UTC), 200, "/v1/today"),
        (datetime(2026, 11, 11, 9, 40, tzinfo=UTC), 500, "/v1/today"),
        (datetime(2026, 11, 11, 0, 0, tzinfo=UTC), 404, "/v1/today"),
        (datetime(2026, 11, 9, 0, 0, tzinfo=UTC), 200, "/v1/week"),
        (datetime(2026, 11, 8, 23, 59, tzinfo=UTC), 200, "/v1/month"),
        (datetime(2026, 11, 1, 0, 0, tzinfo=UTC), 200, "/v1/month"),
        (datetime(2026, 10, 31, 23, 59, tzinfo=UTC), 200, "/v1/old"),
    ]
    for when, status, url in calls:
        db_session.add(
            ApiLog(method="GET", endpoint_url=url, status_code=status, latency_ms=10, log_timestamp=when)
        )
    db_session.commit()


def _dashboard(client, headers, **params):
    response = client.get("/oan/admin/auth/dashboard", headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _urls(data):
    return {item["endpoint_url"] for item in data["top_endpoints"]}


def test_today_is_hourly_from_midnight(client, admin_headers, traffic):
    data = _dashboard(client, admin_headers, period="today")

    assert data["period"] == "today"
    assert data["api_health"]["total_calls"] == 3
    assert data["api_health"]["success"] == 1
    assert data["api_health"]["client_errors"] == 1
    assert data["api_health"]["server_errors"] == 1
    assert _urls(data) == {"/v1/today"}
    trend = data["api_usage_trend"]
    assert [point["label"] for point in trend] == [f"{hour:02d}:00" for hour in range(16)]
    assert trend[0]["value"] == 1
    assert trend[9]["value"] == 2
    assert sum(point["value"] for point in trend) == 3


def test_week_starts_on_monday(client, admin_headers, traffic):
    data = _dashboard(client, admin_headers, period="week")

    assert data["api_health"]["total_calls"] == 4
    assert _urls(data) == {"/v1/today", "/v1/week"}
    assert [(point["label"], point["value"]) for point in data["api_usage_trend"]] == [
        ("2026-11-09", 1),
        ("2026-11-10", 0),
        ("2026-11-11", 3),
    ]


@pytest.mark.parametrize("params", [{"period": "month"}, {}])
def test_month_starts_on_the_first_and_is_the_default(client, admin_headers, traffic, params):
    data = _dashboard(client, admin_headers, **params)

    assert data["period"] == "month"
    assert data["api_health"]["total_calls"] == 6
    assert "/v1/old" not in _urls(data)
    trend = data["api_usage_trend"]
    assert len(trend) == 11
    assert trend[0] == {"label": "2026-11-01", "value": 1}
    assert trend[-1] == {"label": "2026-11-11", "value": 3}


def test_unknown_period_is_rejected(client, admin_headers):
    response = client.get("/oan/admin/auth/dashboard", headers=admin_headers, params={"period": "year"})
    assert response.status_code in (400, 422)
