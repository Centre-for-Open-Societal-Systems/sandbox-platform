"""Portal registration and sign-in.

The flow under test: one signup form, then an emailed code. Verifying the code
activates the account and grants sandbox access with no administrator in the
loop. UAT and production are separate, reviewed requests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.participant import Participant
from tests.conftest import PARTICIPANT_PASSWORD

SIGNUP_PAYLOAD = {
    "first_name": "Abebe",
    "last_name": "Bekele",
    "country_code": "ET",
    "mobile_number": "0911234567",
    "email_id": "ops@greenfields.et",
    "category_id": 1,
    "company_name": "Greenfields PLC",
    "password": "Greenfields1#",
    "declaration": True,
}


def _signup(client, **overrides) -> dict:
    response = client.post(
        "/oan/participant/auth/signup", json={**SIGNUP_PAYLOAD, **overrides}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _verify(client, db_session, data) -> Participant:
    user = db_session.query(Participant).filter_by(unique_id=data["unique_id"]).one()
    response = client.post(
        "/oan/participant/auth/verify-email",
        json={"unique_id": data["unique_id"], "otp": user.otp},
    )
    assert response.status_code == 200, response.text
    db_session.refresh(user)
    return user


# ------------------------------------------------------------------ signup
def test_signup_creates_an_unverified_account(client, db_session):
    data = _signup(client)

    assert data["unique_id"]
    assert data["masked_email"].endswith("@greenfields.et")
    assert "ops@" not in data["masked_email"]

    user = db_session.query(Participant).one()
    assert user.is_email_verified is False
    assert user.first_name == "Abebe"
    assert user.company_name == "Greenfields PLC"
    # The mobile number is stored in E.164 form regardless of how it was typed.
    assert user.mobile_number == "+251911234567"
    assert user.user_pass != SIGNUP_PAYLOAD["password"]


def test_signup_does_not_grant_any_environment_before_verification(client, db_session):
    _signup(client)

    user = db_session.query(Participant).one()
    assert user.is_sandbox_approved is False
    assert user.is_uat_approved is False
    assert user.is_prod_approved is False


def test_signup_requires_accepting_the_terms(client):
    response = client.post(
        "/oan/participant/auth/signup", json={**SIGNUP_PAYLOAD, "declaration": False}
    )

    assert response.status_code == 400


def test_signup_rejects_a_weak_password(client):
    response = client.post(
        "/oan/participant/auth/signup", json={**SIGNUP_PAYLOAD, "password": "password"}
    )

    assert response.status_code == 400


def test_signup_rejects_a_malformed_ethiopian_mobile_number(client):
    response = client.post(
        "/oan/participant/auth/signup",
        json={**SIGNUP_PAYLOAD, "mobile_number": "12345"},
    )

    assert response.status_code == 400


def test_email_address_cannot_be_registered_twice(client):
    _signup(client)

    duplicate = client.post("/oan/participant/auth/signup", json=SIGNUP_PAYLOAD)
    assert duplicate.status_code == 409

    check = client.post(
        "/oan/participant/auth/check-email",
        json={"email_id": SIGNUP_PAYLOAD["email_id"]},
    )
    assert check.json()["data"]["available"] is False


# ------------------------------------------------------ email verification
def test_verification_activates_the_account_and_opens_the_sandbox(client, db_session):
    data = _signup(client)
    issued = db_session.query(Participant).filter_by(unique_id=data["unique_id"]).one().otp
    # Any code other than the issued one (which is 000000 while mail is off).
    wrong_code = "111111" if issued != "111111" else "222222"

    wrong = client.post(
        "/oan/participant/auth/verify-email",
        json={"unique_id": data["unique_id"], "otp": wrong_code},
    )
    assert wrong.status_code == 400

    user = _verify(client, db_session, data)
    assert user.is_email_verified is True
    assert user.is_sandbox_approved is True
    # Sandbox only - the other two environments still need a decision.
    assert user.is_uat_approved is False
    assert user.is_prod_approved is False


def test_expired_code_is_rejected(client, db_session):
    data = _signup(client)
    user = db_session.query(Participant).one()
    user.otp_generated_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()

    response = client.post(
        "/oan/participant/auth/verify-email",
        json={"unique_id": data["unique_id"], "otp": user.otp},
    )

    assert response.status_code == 400
    assert "expired" in response.json()["message"].lower()


def test_login_is_refused_until_the_email_is_verified(client):
    _signup(client)

    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": SIGNUP_PAYLOAD["email_id"],
            "password": SIGNUP_PAYLOAD["password"],
        },
    )

    assert response.status_code == 401
    assert "verify" in response.json()["message"].lower()


def test_signup_then_verify_then_login(client, db_session):
    """The whole happy path, end to end."""
    data = _signup(client)
    _verify(client, db_session, data)

    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": SIGNUP_PAYLOAD["email_id"],
            "password": SIGNUP_PAYLOAD["password"],
        },
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["access_token"]
    assert body["environments"] == ["SANDBOX"]
    assert body["is_profile_complete"] is False


# ------------------------------------------------------------------- login
def test_login_accepts_the_email_address(client, verified_participant):
    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": verified_participant.email_id,
            "password": PARTICIPANT_PASSWORD,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["environments"] == ["SANDBOX"]


def test_login_is_case_insensitive_on_the_email_address(client, verified_participant):
    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": verified_participant.email_id.upper(),
            "password": PARTICIPANT_PASSWORD,
        },
    )

    assert response.status_code == 200


def test_login_blocked_for_a_rejected_account(client, db_session, verified_participant):
    verified_participant.is_rejected = True
    verified_participant.rejection_reason = "Registration documents were incomplete."
    db_session.commit()

    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": verified_participant.email_id,
            "password": PARTICIPANT_PASSWORD,
        },
    )

    assert response.status_code == 401
    assert response.json()["message"] == "Registration documents were incomplete."


def test_login_blocked_for_a_disabled_account(client, db_session, verified_participant):
    verified_participant.is_enabled = False
    db_session.commit()

    response = client.post(
        "/oan/participant/auth/login",
        json={
            "email_id": verified_participant.email_id,
            "password": PARTICIPANT_PASSWORD,
        },
    )

    assert response.status_code == 401


def test_wrong_password_is_refused(client, verified_participant):
    response = client.post(
        "/oan/participant/auth/login",
        json={"email_id": verified_participant.email_id, "password": "Wr0ng#Password"},
    )

    assert response.status_code == 401


def test_forgot_password_does_not_reveal_whether_the_account_exists(client):
    known = client.post(
        "/oan/participant/auth/forgot-password", json={"email_id": "nobody@example.org"}
    )

    assert known.status_code == 200
    assert "if the account exists" in known.json()["message"].lower()


# ----------------------------------------------------------------- profile
def test_profile_is_scoped_to_the_signed_in_user(client, participant_headers):
    response = client.get("/oan/participant/profile", headers=participant_headers)

    assert response.status_code == 200
    assert response.json()["data"]["email_id"] == "partner@example.org"


def test_uat_request_is_refused_while_the_profile_is_incomplete(
    client, participant_headers
):
    response = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "UAT"},
    )

    assert response.status_code == 400
    assert "complete your profile" in response.json()["message"].lower()


def test_promotion_to_production_requires_uat_first(client, participant_headers):
    response = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "PRODUCTION"},
    )

    assert response.status_code == 400
    assert "UAT" in response.json()["message"]


def test_completing_the_profile_unlocks_the_uat_request(
    client, db_session, verified_participant, participant_headers
):
    response = client.put(
        "/oan/participant/profile",
        headers=participant_headers,
        data={
            "profile_type": "ORGANIZATION",
            "company_name": "Test Agri Partner PLC",
            "organization_registration_number": "ET/AA/123456",
            "admin_area_code_l1": "ET-AA",
            "participant_type_id": 2,
            "service_domain": "Advisory",
            "authorized_person_name": "Abebe Bekele",
            "authorized_person_designation": "Director",
            "description": "Advisory services for smallholder farmers.",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_profile_complete"] is True

    promotion = client.post(
        "/oan/participant/promotion-requests",
        headers=participant_headers,
        data={"target_environment": "UAT"},
    )
    assert promotion.status_code == 200, promotion.text

    db_session.refresh(verified_participant)
    assert verified_participant.is_uat_requested is True
    assert verified_participant.is_uat_approved is False


def test_users_cannot_reach_admin_routes(client, participant_headers):
    response = client.post(
        "/oan/admin/participants/list",
        headers=participant_headers,
        json={"page": 1, "limit": 10},
    )

    assert response.status_code == 401
