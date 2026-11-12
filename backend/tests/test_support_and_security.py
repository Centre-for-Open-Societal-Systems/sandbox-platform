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
from tests.keys import RSA_KEY, certificate, public_pem

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
        is_uat_requested=True,
        is_uat_approved=True,
    )
    db_session.add(other)
    db_session.commit()
    return other


# ------------------------------------------------------- password recovery
def test_participant_can_reset_a_forgotten_password(
    client, db_session, verified_participant, mailbox
):
    client.post(
        "/oan/participant/auth/forgot-password",
        json={"email_id": verified_participant.email_id},
    )
    db_session.refresh(verified_participant)
    token = mailbox[-1]["values"]["token"]
    # Only the hash is kept in the database.
    assert token and verified_participant.reset_pass_token not in (None, token)

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


def test_admin_set_password_rejects_a_weak_password(
    client, db_session, master_admin, mailbox
):
    client.post(
        "/oan/admin/auth/forgot-password", json={"email_id": master_admin.email_id}
    )
    token = mailbox[-1]["values"]["token"]

    weak = client.post(
        "/oan/admin/auth/set-password",
        json={"token": token, "new_password": "alllowercase"},
    )
    assert weak.status_code == 400

    strong = client.post(
        "/oan/admin/auth/set-password",
        json={"token": token, "new_password": "Str0ng#Admin"},
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
        "public_key": public_pem(RSA_KEY),
        "endpoint_ids": [1, 2],
        "daily_volume": 5000,
        "integration_contact": "Abebe, +251911234567",
        "escalation_contact": "ops@example.org",
    }
    response = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "PRODUCTION", "extra_data": json.dumps(details)},
        files={"certificate": ("client.pem", certificate(), "text/plain")},
    )
    assert response.status_code == 200, response.text

    request = db_session.query(ParticipantRequestInfo).one()
    key = request.extra_data.pop("key")
    assert request.extra_data == {**details, "public_key": public_pem(RSA_KEY).strip()}
    assert key["source"] == "certificate" and key["algorithm"] == "RSA 2048"
    assert key["certificate"]["common_name"] == "partner.example.org"
    assert len(key["fingerprint_sha256"].split(":")) == 32
    assert request.certificate_path.endswith("client.pem")

    listed = client.get("/oan/participant/promotion-requests", headers=participant_headers)
    assert listed.json()["data"][0]["extra_data"]["daily_volume"] == 5000


def test_environment_request_rejects_unknown_details_and_private_keys(
    client, upload_dir, participant_headers
):
    unknown = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "PRODUCTION", "extra_data": json.dumps({"x": 1})},
    )
    assert unknown.status_code == 400
    assert "extra" in unknown.json()["message"].lower()

    private_key = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "PRODUCTION"},
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
        data={"target_environment": "PRODUCTION",
              "extra_data": json.dumps({"daily_volume": 10, "public_key": public_pem(RSA_KEY)})},
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
    assert data["requests"][0]["target_environment"] == "PRODUCTION"
    extra = data["requests"][0]["extra_data"]
    assert extra["daily_volume"] == 10
    assert extra["key"]["source"] == "public_key" and extra["key"]["algorithm"] == "RSA 2048"

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


def _login(client, user: dict):
    return client.post(
        "/oan/participant/auth/login",
        json={"email_id": user["email_id"], "password": user["password"]},
    )


def test_signup_while_mail_is_off_waits_for_admin_approval(
    client, db_session, monkeypatch, admin_headers
):
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    signup = client.post("/oan/participant/auth/signup", json=SIGNUP)
    assert signup.status_code == 200, signup.text
    data = signup.json()["data"]
    assert data["requires_verification"] is False
    assert data["pending_approval"] is True

    user = db_session.query(Participant).filter_by(unique_id=data["unique_id"]).one()
    assert user.is_email_verified is True
    assert user.otp is None
    assert user.is_uat_requested is True
    assert user.is_uat_approved is False

    refused = _login(client, SIGNUP)
    assert refused.status_code == 401
    assert "waiting for UAT approval" in refused.json()["message"]

    pending = client.post(
        "/oan/admin/participants/pending?environment=UAT", headers=admin_headers, json={}
    ).json()["data"]["participants"]
    assert [row["email_id"] for row in pending] == [SIGNUP["email_id"]]

    approved = client.post(
        "/oan/admin/participants/approve",
        headers=admin_headers,
        json={"participant_id": user.participant_id, "environment": "UAT"},
    )
    assert approved.status_code == 200, approved.text
    login = _login(client, SIGNUP)
    assert login.status_code == 200, login.text
    assert login.json()["data"]["environments"] == ["UAT"]


def test_admin_can_reject_a_registration_while_mail_is_off(
    client, db_session, monkeypatch, admin_headers
):
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    data = client.post("/oan/participant/auth/signup", json=SIGNUP).json()["data"]
    user = db_session.query(Participant).filter_by(unique_id=data["unique_id"]).one()

    rejected = client.post(
        "/oan/admin/participants/reject",
        headers=admin_headers,
        json={
            "participant_id": user.participant_id,
            "environment": "UAT",
            "rejection_reason": "Company could not be confirmed.",
        },
    )
    assert rejected.status_code == 200, rejected.text
    refused = _login(client, SIGNUP)
    assert refused.status_code == 401
    assert refused.json()["message"] == "Company could not be confirmed."


def test_unverified_signup_from_before_is_approvable_while_mail_is_off(
    client, db_session, monkeypatch, admin_headers
):
    # Registered with the code flow, never received the code, then mail stayed off.
    monkeypatch.setattr(settings, "MAIL_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(
        "app.services.notification_service.send_email", lambda *args, **kwargs: True
    )
    data = client.post("/oan/participant/auth/signup", json=SIGNUP).json()["data"]
    assert data["requires_verification"] is True
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)

    refused = _login(client, SIGNUP)
    assert "waiting for UAT approval" in refused.json()["message"]
    pending = client.post(
        "/oan/admin/participants/pending?environment=UAT", headers=admin_headers, json={}
    ).json()["data"]["participants"]
    user = db_session.query(Participant).filter_by(unique_id=data["unique_id"]).one()
    assert [row["participant_id"] for row in pending] == [user.participant_id]

    client.post(
        "/oan/admin/participants/approve",
        headers=admin_headers,
        json={"participant_id": user.participant_id, "environment": "UAT"},
    )
    db_session.refresh(user)
    assert user.is_email_verified is True
    assert _login(client, SIGNUP).status_code == 200


@pytest.mark.parametrize(
    ("mail_enabled", "env"), [(True, "sandbox"), (False, "production")]
)
def test_real_codes_when_mail_is_on_or_in_production(
    client, db_session, monkeypatch, mail_enabled, env
):
    monkeypatch.setattr(settings, "MAIL_ENABLED", mail_enabled)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test")
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
    # Developer machine only.
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    monkeypatch.setattr(settings, "ENV", "local")
    monkeypatch.setattr(settings, "DEV_FIXED_OTP", "000000")
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


@pytest.mark.parametrize("env", ["local", "sandbox"])
def test_admin_password_is_never_reset_with_a_code(client, monkeypatch, master_admin, env):
    """The fixed code used to let anyone take over the master administrator."""
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    monkeypatch.setattr(settings, "ENV", env)
    monkeypatch.setattr(settings, "DEV_FIXED_OTP", "000000")
    forgot = client.post(
        "/oan/admin/auth/forgot-password", json={"email_id": master_admin.email_id}
    )
    assert forgot.json()["data"]["is_fixed_otp"] is False

    response = _reset_with_code(
        client, "/oan/admin/auth/set-password", master_admin.email_id
    )
    assert response.status_code == 400
    login = client.post(
        "/oan/admin/auth/login",
        json={"username": master_admin.email_id, "password": "Fresh#Pass2026"},
    )
    assert login.status_code == 401


def test_participant_fixed_code_is_off_outside_a_developer_machine(
    client, monkeypatch, verified_participant
):
    monkeypatch.setattr(settings, "MAIL_ENABLED", False)
    monkeypatch.setattr(settings, "ENV", "sandbox")
    monkeypatch.setattr(settings, "DEV_FIXED_OTP", "000000")
    email = verified_participant.email_id
    forgot = client.post("/oan/participant/auth/forgot-password", json={"email_id": email})
    assert forgot.json()["data"]["is_fixed_otp"] is False
    response = _reset_with_code(client, "/oan/participant/auth/reset-password", email)
    assert response.status_code == 400


def test_reset_needs_a_token_or_email_and_code(client):
    response = client.post(
        "/oan/participant/auth/reset-password", json={"new_password": "Fresh#Pass2026"}
    )
    assert response.status_code == 400


def test_production_request_needs_a_valid_key_and_approval_makes_it_the_partners(
    client, upload_dir, db_session, verified_participant, participant_headers, admin_headers
):
    assert client.put("/oan/participant/profile", headers=participant_headers, data=COMPLETE_PROFILE).status_code == 200

    def ask(**files_and_key):
        key = files_and_key.pop("public_key", None)
        return client.post(
            "/oan/participant/promotion-requests",
            headers=participant_headers,
            data={"target_environment": "PRODUCTION",
                  "extra_data": json.dumps({"public_key": key} if key else {})},
            files=files_and_key or None,
        )

    missing = ask()
    assert missing.status_code == 400 and "Upload your certificate" in missing.json()["message"]
    garbage = ask(certificate=("client.crt", b"-----BEGIN CERTIFICATE-----x", "text/plain"))
    assert garbage.status_code == 400 and "certificate could not be read" in garbage.json()["message"]
    pdf = ask(certificate=("certificate.pdf", b"%PDF-1.4", "application/pdf"))
    assert pdf.status_code == 400 and "file type '.pdf'" in pdf.json()["message"].lower()
    assert db_session.query(ParticipantRequestInfo).count() == 0  # nothing kept from refused requests

    assert ask(public_key=public_pem(RSA_KEY)).status_code == 200
    approved = client.post("/oan/admin/participants/approve", headers=admin_headers,
                           json={"participant_id": verified_participant.participant_id, "environment": "PRODUCTION"})
    assert approved.status_code == 200, approved.text
    db_session.refresh(verified_participant)
    assert verified_participant.public_key == public_pem(RSA_KEY).strip()
