"""Password recovery, support queries, private files and other 13 Oct fixes."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.config.settings import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import create_app
from app.models.admin import AdmUser
from app.models.participant import Participant, ParticipantRequestInfo
from tests.conftest import ADMIN_PASSWORD, PARTICIPANT_PASSWORD

COMPLETE_PROFILE = {
    "profile_type": "ORGANIZATION",
    "company_name": "Test Agri Partner PLC",
    "organization_registration_number": "ET/AA/123456",
    "admin_area_code_l1": "ET-AA",
    "participant_type_id": 2,
    "service_domain": "Advisory",
    "authorized_person_name": "Abebe Bekele",
    "authorized_person_designation": "Director",
    "description": "Advisory services for smallholder farmers.",
}


def _login_participant(client, email: str, password: str) -> dict:
    response = client.post(
        "/oan/participant/auth/login", json={"email_id": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _second_participant(db_session) -> Participant:
    other = Participant(
        first_name="Other",
        last_name="Partner",
        email_id="other@example.org",
        mobile_number="+251911000000",
        company_name="Other Co",
        category_id=1,
        user_pass=hash_password(PARTICIPANT_PASSWORD),
        country_code="ET",
        declaration=True,
        is_email_verified=True,
        is_approved=1,
        is_activated=1,
        is_sandbox_approved=True,
    )
    db_session.add(other)
    db_session.commit()
    return other


# ------------------------------------------------------- password recovery
def test_participant_can_reset_a_forgotten_password(
    client, db_session, verified_participant
):
    client.post(
        "/oan/participant/auth/forgot-password",
        json={"email_id": verified_participant.email_id},
    )
    db_session.refresh(verified_participant)
    token = verified_participant.reset_pass_token
    assert token

    reset = client.post(
        "/oan/participant/auth/reset-password",
        json={"token": token, "new_password": "Brand#New2026"},
    )
    assert reset.status_code == 200, reset.text
    _login_participant(client, verified_participant.email_id, "Brand#New2026")

    reused = client.post(
        "/oan/participant/auth/reset-password",
        json={"token": token, "new_password": "Another#New2026"},
    )
    assert reused.status_code == 404


def test_admin_set_password_rejects_a_weak_password(client, db_session, master_admin):
    client.post(
        "/oan/admin/auth/forgot-password", json={"email_id": master_admin.email_id}
    )
    db_session.refresh(master_admin)

    weak = client.post(
        "/oan/admin/auth/set-password",
        json={"token": master_admin.set_pass_token, "new_password": "alllowercase"},
    )
    assert weak.status_code == 400

    strong = client.post(
        "/oan/admin/auth/set-password",
        json={"token": master_admin.set_pass_token, "new_password": "Str0ng#Admin"},
    )
    assert strong.status_code == 200, strong.text


def test_admin_can_set_another_admins_password(
    client, db_session, master_admin, admin_headers
):
    created = client.post(
        "/oan/admin/users",
        headers=admin_headers,
        json={
            "first_name": "Second",
            "email_id": "second@example.org",
            "login_name": "secondadmin",
            "role_id": master_admin.role_id,
        },
    )
    assert created.status_code == 200, created.text
    admin_id = created.json()["data"]["admin_id"]

    updated = client.put(
        "/oan/admin/users",
        headers=admin_headers,
        json={"admin_id": admin_id, "password": "Second#Pass1"},
    )
    assert updated.status_code == 200, updated.text

    user = db_session.get(AdmUser, admin_id)
    db_session.refresh(user)
    assert user.is_activated is True
    assert user.set_pass_token is None
    login = client.post(
        "/oan/admin/auth/login",
        json={"username": "second@example.org", "password": "Second#Pass1"},
    )
    assert login.status_code == 200, login.text


# ------------------------------------------------------------ refresh token
def test_refresh_needs_a_real_refresh_token_on_a_live_session(
    client, verified_participant
):
    session = _login_participant(client, verified_participant.email_id, PARTICIPANT_PASSWORD)
    auth = {"x-auth-key": session["auth_key"]}

    refreshed = client.post(
        "/oan/participant/auth/refresh",
        headers=auth,
        json={"refresh_token": session["refresh_token"]},
    )
    assert refreshed.status_code == 200, refreshed.text
    assert refreshed.json()["data"]["access_token"]

    # An access token is not a refresh token.
    wrong = client.post(
        "/oan/participant/auth/refresh",
        headers=auth,
        json={"refresh_token": session["access_token"]},
    )
    assert wrong.status_code == 401

    client.post(
        "/oan/participant/auth/logout",
        headers={**auth, "x-access-token": session["access_token"]},
    )
    after_logout = client.post(
        "/oan/participant/auth/refresh",
        headers=auth,
        json={"refresh_token": session["refresh_token"]},
    )
    assert after_logout.status_code == 401


# ------------------------------------------------------------ private files
@pytest.fixture
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    (tmp_path / "participants" / "id-proof").mkdir(parents=True)
    (tmp_path / "products" / "icons").mkdir(parents=True)
    (tmp_path / "participants" / "id-proof" / "proof.pdf").write_bytes(b"%PDF-proof")
    (tmp_path / "products" / "icons" / "icon.png").write_bytes(b"png")
    return tmp_path


def test_participant_documents_are_not_public(
    client, db_session, upload_dir, verified_participant, participant_headers, admin_headers
):
    verified_participant.id_proof = "participants/id-proof/proof.pdf"
    db_session.commit()
    url = "/oan/files/participants/id-proof/proof.pdf"

    assert client.get(url).status_code == 401
    assert client.get(url, headers=participant_headers).status_code == 200
    assert client.get(url, headers=admin_headers).status_code == 200

    other = _second_participant(db_session)
    other_session = _login_participant(client, other.email_id, PARTICIPANT_PASSWORD)
    other_headers = {
        "x-access-token": other_session["access_token"],
        "x-auth-key": other_session["auth_key"],
    }
    assert client.get(url, headers=other_headers).status_code == 403


def test_catalogue_assets_stay_public(client, upload_dir):
    response = client.get("/oan/files/products/icons/icon.png")
    assert response.status_code == 200
    assert response.content == b"png"


# ---------------------------------------------------------- support queries
def test_support_query_round_trip(
    client, db_session, verified_participant, participant_headers, admin_headers
):
    created = client.post(
        "/oan/participant/queries",
        headers=participant_headers,
        json={
            "subject": "Token expired",
            "description": "My sandbox token expires too quickly.",
            "query_type": 1,
        },
    )
    assert created.status_code == 200, created.text
    query_id = created.json()["data"]["query_id"]

    listed = client.post(
        "/oan/admin/participants/queries/list",
        headers=admin_headers,
        json={"page": 1, "limit": 10, "search": "agri partner"},
    )
    assert listed.status_code == 200, listed.text
    rows = listed.json()["data"]["queries"]
    assert [row["query_id"] for row in rows] == [query_id]
    assert rows[0]["participant_name"] == "Test Partner"
    assert rows[0]["email_id"] == "partner@example.org"
    assert rows[0]["company_name"] == "Test Agri Partner PLC"

    answered = client.post(
        "/oan/admin/participants/queries/respond",
        headers=admin_headers,
        json={"query_id": query_id, "response": "Use the refresh token.", "status": 2},
    )
    assert answered.status_code == 200, answered.text

    open_only = client.post(
        "/oan/admin/participants/queries/list",
        headers=admin_headers,
        json={"page": 1, "limit": 10, "status": 0},
    )
    assert open_only.json()["data"]["queries"] == []

    mine = client.get("/oan/participant/queries", headers=participant_headers)
    assert mine.json()["data"][0]["response"] == "Use the refresh token."
    assert mine.json()["data"][0]["status"] == 2


# --------------------------------------------------------- promotion details
def test_environment_request_keeps_the_production_details(
    client, upload_dir, db_session, verified_participant, participant_headers
):
    profile = client.put(
        "/oan/participant/profile", headers=participant_headers, data=COMPLETE_PROFILE
    )
    assert profile.status_code == 200, profile.text

    details = {
        "public_key": "-----BEGIN PUBLIC KEY-----abc-----END PUBLIC KEY-----",
        "endpoint_ids": [1, 2],
        "daily_volume": 5000,
        "integration_contact": "Abebe, +251911234567",
        "escalation_contact": "ops@example.org",
    }
    response = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "UAT", "extra_data": json.dumps(details)},
        files={"certificate": ("client.pem", b"-----BEGIN CERTIFICATE-----", "text/plain")},
    )
    assert response.status_code == 200, response.text

    request = db_session.query(ParticipantRequestInfo).one()
    assert request.extra_data == details
    assert request.certificate_path.endswith("client.pem")

    listed = client.get("/oan/participant/promotion-requests", headers=participant_headers)
    assert listed.json()["data"][0]["extra_data"]["daily_volume"] == 5000


def test_environment_request_rejects_unknown_details_and_private_keys(
    client, upload_dir, participant_headers
):
    unknown = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "UAT", "extra_data": json.dumps({"x": 1})},
    )
    assert unknown.status_code == 400
    assert "extra" in unknown.json()["message"].lower()

    private_key = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "UAT"},
        files={"certificate": ("client.key", b"secret", "text/plain")},
    )
    assert private_key.status_code == 400
    assert "file type '.key'" in private_key.json()["message"].lower()


# --------------------------------------------------------- database outage
def test_database_outage_answers_503(db_session):
    def broken_db():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    application = create_app()
    application.dependency_overrides[get_db] = broken_db
    with TestClient(application) as client:
        response = client.post(
            "/oan/admin/auth/login",
            json={"username": "admin@example.org", "password": ADMIN_PASSWORD},
        )
    assert response.status_code == 503
    assert response.json()["status"] is False


def test_admin_detail_shows_documents_and_requests(
    client, db_session, upload_dir, verified_participant, participant_headers, admin_headers
):
    client.put("/oan/participant/profile", headers=participant_headers, data=COMPLETE_PROFILE)
    client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "UAT", "extra_data": json.dumps({"daily_volume": 10})},
    )
    verified_participant.id_proof = "participants/id-proof/proof.pdf"
    db_session.commit()

    detail = client.get(
        f"/oan/admin/participants/{verified_participant.participant_id}",
        headers=admin_headers,
    )
    assert detail.status_code == 200, detail.text
    data = detail.json()["data"]
    assert data["id_proof"] == "participants/id-proof/proof.pdf"
    assert data["requests"][0]["target_environment"] == "UAT"
    assert data["requests"][0]["extra_data"] == {"daily_volume": 10}

    proof = client.get("/oan/files/participants/id-proof/proof.pdf", headers=admin_headers)
    assert proof.headers["content-type"] == "application/pdf"
    assert proof.headers["content-disposition"].startswith("inline")


@pytest.mark.parametrize("digest_name", ["SHA256", "SHA1"])
def test_sealed_login_accepts_both_oaep_digests(
    client, tmp_path, monkeypatch, verified_participant, digest_name
):
    import base64

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "private_key.pem"
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setattr(settings, "RSA_PAYLOAD_ENABLED", True)
    monkeypatch.setattr(settings, "RSA_PRIVATE_KEY_PATH", str(key_path))

    digest = getattr(hashes, digest_name)
    sealed = key.public_key().encrypt(
        json.dumps(
            {"email_id": verified_participant.email_id, "password": PARTICIPANT_PASSWORD}
        ).encode(),
        padding.OAEP(mgf=padding.MGF1(algorithm=digest()), algorithm=digest(), label=None),
    )
    response = client.post(
        "/oan/participant/auth/login/sealed",
        json={"post_data": base64.b64encode(sealed).decode()},
    )
    assert response.status_code == 200, response.text


# ------------------------------------------------------ development OTP
SIGNUP = {
    "first_name": "Dev",
    "last_name": "Tester",
    "country_code": "ET",
    "mobile_number": "0911000111",
    "email_id": "dev.tester@example.org",
    "category_id": 1,
    "company_name": "Dev Test PLC",
    "password": "DevTest#2026",
    "declaration": True,
}


def test_signup_uses_the_fixed_code_while_mail_is_off(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    signup = client.post("/oan/participant/auth/signup", json=SIGNUP)
    assert signup.status_code == 200, signup.text
    data = signup.json()["data"]
    assert data["is_fixed_otp"] is True

    verify = client.post(
        "/oan/participant/auth/verify-email",
        json={"unique_id": data["unique_id"], "otp": "000000"},
    )
    assert verify.status_code == 200, verify.text

    resend_user = {**SIGNUP, "email_id": "second.dev@example.org", "mobile_number": "0911000222"}
    second = client.post("/oan/participant/auth/signup", json=resend_user).json()["data"]
    resend = client.post(
        "/oan/participant/auth/resend-otp", json={"unique_id": second["unique_id"]}
    )
    assert resend.json()["data"]["is_fixed_otp"] is True
    user = db_session.query(Participant).filter_by(unique_id=second["unique_id"]).one()
    assert user.otp == "000000"


@pytest.mark.parametrize(
    ("mail_enabled", "env"), [(True, "sandbox"), (False, "production")]
)
def test_real_codes_when_mail_is_on_or_in_production(
    client, db_session, monkeypatch, mail_enabled, env
):
    monkeypatch.setattr(settings, "MAIL_ENABLED", mail_enabled)
    monkeypatch.setattr(settings, "ENV", env)
    monkeypatch.setattr(
        "app.services.participant_auth_service.send_otp", lambda *args, **kwargs: True
    )
    data = client.post("/oan/participant/auth/signup", json=SIGNUP).json()["data"]
    assert data["is_fixed_otp"] is False
    # Random codes: 20 draws are never all the fixed value.
    from app.core.security import generate_otp

    assert any(generate_otp() != "000000" for _ in range(20))


def test_fixed_code_must_be_six_digits():
    from app.config.settings import Settings

    with pytest.raises(ValueError):
        Settings(DEV_FIXED_OTP="12ab")
    assert Settings(DEV_FIXED_OTP="").fixed_otp is None


# ---------------------------------------- development password reset code
def _reset_with_code(client, path, email, otp="000000", password="Fresh#Pass2026"):
    return client.post(path, json={"email_id": email, "otp": otp, "new_password": password})


def test_participant_resets_password_with_the_fixed_code(
    client, monkeypatch, verified_participant
):
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    path = "/oan/participant/auth/reset-password"
    email = verified_participant.email_id

    # Nothing requested yet: the code alone does not reset anything.
    assert _reset_with_code(client, path, email).status_code == 400

    forgot = client.post("/oan/participant/auth/forgot-password", json={"email_id": email})
    assert forgot.json()["data"]["is_fixed_otp"] is True

    assert _reset_with_code(client, path, email, otp="123456").status_code == 400
    assert _reset_with_code(client, path, email).status_code == 200
    _login_participant(client, email, "Fresh#Pass2026")
    # One use only: the pending reset is cleared.
    assert _reset_with_code(client, path, email, password="Other#Pass2026").status_code == 400


def test_reset_code_is_refused_once_mail_is_on(client, monkeypatch, verified_participant):
    monkeypatch.setattr(settings, "MAIL_ENABLED", True)
    monkeypatch.setattr(
        "app.services.participant_auth_service.send_templated", lambda *a, **k: True
    )
    email = verified_participant.email_id
    forgot = client.post("/oan/participant/auth/forgot-password", json={"email_id": email})
    assert forgot.json()["data"]["is_fixed_otp"] is False
    response = _reset_with_code(client, "/oan/participant/auth/reset-password", email)
    assert response.status_code == 400


def test_admin_resets_password_with_the_fixed_code(client, monkeypatch, master_admin):
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    forgot = client.post(
        "/oan/admin/auth/forgot-password", json={"email_id": master_admin.email_id}
    )
    assert forgot.json()["data"]["is_fixed_otp"] is True

    response = _reset_with_code(
        client, "/oan/admin/auth/set-password", master_admin.email_id
    )
    assert response.status_code == 200, response.text
    login = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.email_id, "password": "Fresh#Pass2026"},
    )
    assert login.status_code == 200, login.text


def test_reset_needs_a_token_or_email_and_code(client):
    response = client.post(
        "/oan/participant/auth/reset-password", json={"new_password": "Fresh#Pass2026"}
    )
    assert response.status_code == 400
