"""Test fixtures.

Each test runs against a fresh in-memory SQLite database. The environment is
configured before any application module is imported so the engine picks up the
test URL rather than the developer's Postgres settings.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATABASE_URL_OVERRIDE", "sqlite://")
# Keep test runs out of the developer's real log file.
os.environ.setdefault("LOG_DIR", tempfile.mkdtemp(prefix="oan-test-logs-"))
os.environ.setdefault("JWT_ACCESS_TOKEN_KEY", "test-access-secret-0123456789abcdef0123")
os.environ.setdefault("JWT_REFRESH_TOKEN_KEY", "test-refresh-secret-0123456789abcdef0123")
os.environ.setdefault("MAIL_ENABLED", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Gateway features start off whatever the developer's .env says; tests switch them on.
for _name, _value in {
    "GATEWAY_LOG_INGEST_ENABLED": "false",
    "GATEWAY_LOG_INGEST_URL": "",
    "GATEWAY_LOG_INGEST_TOKEN": "",
    "GATEWAY_RATE_LIMIT_ENABLED": "false",
    "GATEWAY_RATE_LIMIT_POLICY": "local",
    "GATEWAY_RATE_LIMIT_REDIS_HOST": "",
    "KEYCLOAK_PROVISIONING_ENABLED": "false",
    "KEYCLOAK_URL": "",
    "KEYCLOAK_PUBLIC_URL": "",
    "KEYCLOAK_ADMIN_CLIENT_SECRET": "",
}.items():
    os.environ.setdefault(_name, _value)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: F401,E402  - registers the tables on Base.metadata
from app.core.database import Base, SessionLocal, engine, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.admin import AdmRole, AdmUser  # noqa: E402
from app.models.participant import Participant  # noqa: E402
from app.repositories.admin_repository import PermissionRepository  # noqa: E402

ADMIN_PASSWORD = "Adm1n#Test"
PARTICIPANT_PASSWORD = "P0rtal#Test"


@pytest.fixture
def db_session():
    """A session on the application engine, with the schema built per test.

    The engine is the in-memory SQLite one configured in conftest, which uses a
    single pooled connection - so application startup and the test share one
    database.
    """
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def client(db_session):
    application = create_app()
    application.dependency_overrides[get_db] = lambda: db_session
    with TestClient(application) as test_client:
        yield test_client
    application.dependency_overrides.clear()


@pytest.fixture
def master_admin(db_session) -> AdmUser:
    PermissionRepository(db_session).sync_catalogue()
    role = AdmRole(role_name="Super Administrator", is_editable=False)
    db_session.add(role)
    db_session.commit()

    admin = AdmUser(
        first_name="Test",
        last_name="Administrator",
        email_id="admin@example.org",
        login_name="testadmin",
        login_pass=hash_password(ADMIN_PASSWORD),
        is_master=True,
        is_activated=True,
        role_id=role.role_id,
        country_code="ET",
    )
    db_session.add(admin)
    db_session.commit()
    return admin


@pytest.fixture
def admin_headers(client, master_admin) -> dict[str, str]:
    response = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.email_id, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {"x-access-token": data["access_token"], "x-auth-key": data["auth_key"]}


@pytest.fixture
def verified_participant(db_session) -> Participant:
    """A portal account past email verification and UAT approval."""
    user = Participant(
        first_name="Test",
        last_name="Partner",
        email_id="partner@example.org",
        mobile_number="+251911234567",
        company_name="Test Agri Partner PLC",
        category_id=1,
        user_pass=hash_password(PARTICIPANT_PASSWORD),
        country_code="ET",
        declaration=True,
        is_email_verified=True,
        is_approved=1,
        is_activated=1,
        is_uat_requested=True,
        is_uat_approved=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def participant_headers(client, verified_participant) -> dict[str, str]:
    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": verified_participant.email_id,
            "password": PARTICIPANT_PASSWORD,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {"x-access-token": data["access_token"], "x-auth-key": data["auth_key"]}


@pytest.fixture
def mailbox(monkeypatch) -> list[dict]:
    """Reset / invitation mails sent during the test: ``{"code", "to", "values"}``.

    Only token hashes are stored, so tests take the token from the mail, as a
    user would.
    """
    sent: list[dict] = []

    def _capture(db, code, to, values, *args, **kwargs):
        sent.append({"code": code, "to": to, "values": dict(values or {})})
        return True

    for module in ("participant_auth_service", "admin_auth_service", "admin_user_service"):
        monkeypatch.setattr(f"app.services.{module}.send_templated", _capture)
    return sent
