# ruff: noqa: F811  (farmer_endpoints is a fixture imported from test_apps)
"""App keys: secret shown once, rotation with a grace period, expiry, and the emails."""

from datetime import UTC, datetime, timedelta

from app.config.settings import settings
from app.models.app import ParticipantAppCredential
from app.services import app_service
from tests.test_apps import (  # noqa: F401 (fixture)
    FakeGateway,
    _api_product,
    _create_app,
    _routes,
    farmer_endpoints,
)


def _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch):
    fake = FakeGateway(_routes()).install(monkeypatch)
    sent = []
    monkeypatch.setattr(
        "app.services.app_service.send_templated",
        lambda db, code, to, values, *a, **k: sent.append((str(code), values)) or True,
    )
    read = _api_product(client, admin_headers, "farmer-read", farmer_endpoints[:2])
    created = _create_app(client, participant_headers, "Mobile App", [read], admin_headers)
    sent.clear()
    return fake, sent, created["app"], created["credential"]


def _url(app_id, credential_id, action):
    return f"/oan/participant/apps/{app_id}/credentials/{credential_id}/{action}"


def test_secret_is_shown_once(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch):
    _, _, app, credential = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    # _create_app already took the one reveal: a second one is refused.
    again = client.post(_url(app["app_id"], credential["credential_id"], "reveal"), headers=participant_headers)
    assert again.status_code == 409
    assert "Rotate" in again.json()["message"]
    # The list never carries the secret.
    listed = client.get(f"/oan/participant/apps/{app['app_id']}", headers=participant_headers).json()["data"]
    assert listed["credentials"][0]["api_secret"] is None and listed["credentials"][0]["secret_viewed"] is True


def test_rotate_keeps_old_key_for_the_grace_period_then_expires_it(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    fake, sent, app, old = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    rotated = client.post(_url(app["app_id"], old["credential_id"], "rotate"), headers=participant_headers)
    assert rotated.status_code == 200, rotated.text
    new = rotated.json()["data"]
    assert new["api_key"] != old["api_key"] and len(new["api_secret"]) >= 40
    assert [code for code, _ in sent] == ["TemplateCode.APP_KEY_ROTATED"] or [c for c, _ in sent] == ["APP_KEY_ROTATED"]
    assert old["api_key"] not in str(sent) and new["api_secret"] not in str(sent)  # mails never carry keys

    rows = {str(r.unique_id): r for r in db_session.query(ParticipantAppCredential).all()}
    old_row = rows[old["credential_id"]]
    assert old_row.expires_date is not None and old_row.status == 1  # still works during the grace period
    consumer = app["gateway_consumer"]
    assert len(fake.credentials[consumer]) == 4  # both keys at the gateway (key-auth + hmac each)

    # Past the grace period the sweep expires it and the gateway drops it.
    old_row.expires_date = datetime.now(UTC) - timedelta(minutes=1)
    db_session.commit()
    sent.clear()
    result = app_service.run_key_maintenance(db_session)
    assert result["expired"] == 1
    db_session.refresh(old_row)
    assert old_row.status == 3
    assert len(fake.credentials[consumer]) == 2
    assert [str(c) for c, _ in sent][-1].endswith("APP_KEY_EXPIRED")
    assert app_service.run_key_maintenance(db_session) == {"expired": 0, "warned": 0}  # idempotent


def test_rotate_with_no_grace_revokes_the_old_key(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "APP_KEY_ROTATION_GRACE_DAYS", 0)
    fake, _, app, old = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    assert client.post(_url(app["app_id"], old["credential_id"], "rotate"), headers=participant_headers).status_code == 200
    statuses = sorted(r.status for r in db_session.query(ParticipantAppCredential).all())
    assert statuses == [1, 2]
    assert len(fake.credentials[app["gateway_consumer"]]) == 2


def test_cannot_rotate_when_the_app_has_the_maximum_keys(
    client, admin_headers, participant_headers, farmer_endpoints, monkeypatch
):
    _, _, app, old = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    assert client.post(f"/oan/participant/apps/{app['app_id']}/credentials", headers=participant_headers).status_code == 201
    blocked = client.post(_url(app["app_id"], old["credential_id"], "rotate"), headers=participant_headers)
    assert blocked.status_code == 422 or blocked.status_code == 400
    assert "Revoke one first" in blocked.json()["message"]


def test_key_lifetime_sets_expiry_and_warns_once(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "APP_KEY_LIFETIME_DAYS", 10)
    monkeypatch.setattr(settings, "APP_KEY_EXPIRY_WARN_DAYS", 14)
    _, sent, app, _ = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    row = db_session.query(ParticipantAppCredential).one()
    assert row.expires_date is not None
    assert app_service.run_key_maintenance(db_session) == {"expired": 0, "warned": 1}
    assert [str(c) for c, _ in sent][-1].endswith("APP_KEY_EXPIRING")
    assert app_service.run_key_maintenance(db_session) == {"expired": 0, "warned": 0}  # warned once


def test_revoking_a_key_emails_the_owner(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch):
    _, sent, app, credential = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    response = client.delete(_url(app["app_id"], credential["credential_id"], "").rstrip("/"), headers=participant_headers)
    assert response.status_code == 200
    assert [str(c) for c, _ in sent][-1].endswith("APP_KEY_REVOKED")


def test_app_shows_calls_used_against_its_limits(
    client, admin_headers, participant_headers, farmer_endpoints, db_session, monkeypatch
):
    from app.models.logs import ApiLog
    from app.services import app_gateway_service

    monkeypatch.setattr(settings, "GATEWAY_RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(app_gateway_service, "effective_limits", lambda app: (60, 5000))
    _, _, app, _ = _setup(client, admin_headers, participant_headers, farmer_endpoints, monkeypatch)
    row = db_session.query(ParticipantAppCredential).one().app
    now = datetime.now(UTC)
    db_session.add_all([
        ApiLog(app_id=row.app_id, log_timestamp=now, source="DIRECT"),
        ApiLog(app_id=row.app_id, log_timestamp=now - timedelta(hours=3), source="DIRECT"),
        ApiLog(app_id=row.app_id, log_timestamp=now - timedelta(days=2), source="DIRECT"),
        ApiLog(app_id=row.app_id + 99, log_timestamp=now, source="DIRECT"),
    ])
    db_session.commit()
    shown = client.get(f"/oan/participant/apps/{app['app_id']}", headers=participant_headers).json()["data"]
    assert shown["calls_last_minute"] == 1 and shown["calls_today"] == 2
    assert shown["quota_per_day"] == 5000
