# ruff: noqa: F811
"""Request id header, support SLA, audit retention and the participant data export."""

from datetime import UTC, datetime, timedelta

from app.config.settings import settings
from app.models.logs import UserActionLog
from app.models.participant import ParticipantQuery
from app.services import log_service
from tests.test_apps import farmer_endpoints  # noqa: F401 (fixture)


def test_request_id_is_echoed_and_made_when_missing(client):
    made = client.get("/oan/health")
    assert made.headers["x-request-id"] == made.headers["x-correlation-id"]
    sent = client.get("/oan/health", headers={"X-Request-Id": "abc-123"})
    assert sent.headers["x-request-id"] == "abc-123" and sent.headers["x-correlation-id"] == "abc-123"
    # An unsafe id is replaced, not echoed.
    bad = client.get("/oan/health", headers={"X-Request-Id": "x" * 200})
    assert bad.headers["x-request-id"] != "x" * 200


def test_support_query_has_a_due_date_and_turns_overdue(client, participant_headers, db_session, monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_SLA_HOURS", 24)
    created = client.post(
        "/oan/participant/queries", headers=participant_headers,
        json={"subject": "Need help", "description": "Which endpoint returns plots?"},
    )
    assert created.status_code in (200, 201), created.text
    [mine] = client.get("/oan/participant/queries", headers=participant_headers).json()["data"]
    assert mine["due_date"] is not None and mine["is_overdue"] is False

    row = db_session.query(ParticipantQuery).one()
    row.added_date = datetime.now(UTC) - timedelta(hours=30)
    db_session.commit()
    [late] = client.get("/oan/participant/queries", headers=participant_headers).json()["data"]
    assert late["is_overdue"] is True
    row.status = 2  # answered: no longer overdue
    db_session.commit()
    [done] = client.get("/oan/participant/queries", headers=participant_headers).json()["data"]
    assert done["is_overdue"] is False

    monkeypatch.setattr(settings, "SUPPORT_SLA_HOURS", 0)  # no SLA configured
    [none] = client.get("/oan/participant/queries", headers=participant_headers).json()["data"]
    assert none["due_date"] is None and none["is_overdue"] is False


def test_audit_retention_deletes_only_old_entries_and_is_off_by_default(db_session):
    now = datetime.now(UTC)
    db_session.add_all([
        UserActionLog(action="OLD", timestamp=now - timedelta(days=400)),
        UserActionLog(action="NEW", timestamp=now - timedelta(days=2)),
    ])
    db_session.commit()
    assert settings.AUDIT_LOG_RETENTION_DAYS == 0
    assert log_service.purge_old_audit_logs(db_session) == 0  # keep forever by default
    assert log_service.purge_old_audit_logs(db_session, days=365) == 1
    assert [r.action for r in db_session.query(UserActionLog).all()] == ["NEW"]


def test_participant_can_download_own_data_without_keys(
    client, participant_headers, admin_headers, farmer_endpoints, monkeypatch
):
    from tests.test_apps import FakeGateway, _api_product, _create_app, _routes

    FakeGateway(_routes()).install(monkeypatch)
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Mobile App", [read], admin_headers)
    key, secret = created["credential"]["api_key"], created["credential"]["api_secret"]

    response = client.get("/oan/participant/profile/export", headers=participant_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert {"profile", "apps", "support_queries", "api_calls", "account_activity", "exported_at"} <= set(data)
    assert [a["name"] for a in data["apps"]] == ["Mobile App"]
    text = response.text
    assert key not in text and secret not in text  # prefixes only
    assert "user_pass" not in text and "reset_pass_token" not in text

