"""Portal registration and authentication endpoints.

Two steps to an account: ``POST /signup`` then ``POST /verify-email``. There
is no username - the business email address is the identifier.
"""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.config.settings import settings
from app.core.deps import CurrentParticipant, DbSession
from app.core.responses import ok
from app.core.security import rsa_decrypt_payload
from app.schemas.common import SealedPayload
from app.schemas.participant import (
    ChangePasswordRequest,
    CheckEmailRequest,
    ForgotPasswordRequest,
    ParticipantLoginRequest,
    RefreshTokenRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    SignupRequest,
    VerifyEmailRequest,
)
from app.services import participant_auth_service

router = APIRouter(prefix="/auth", tags=["User / Auth"])


@router.post("/check-email")
def check_email(payload: CheckEmailRequest, db: DbSession):
    available = participant_auth_service.is_email_available(db, payload.email_id)
    return ok(
        "Email address is available."
        if available
        else "An account with this email address already exists.",
        {"available": available},
    )


@router.post("/signup")
def signup(payload: SignupRequest, db: DbSession):
    return ok(
        "Account created. Check your email for the verification code.",
        participant_auth_service.signup(db, payload),
    )


@router.post("/verify-email")
def verify_email(payload: VerifyEmailRequest, db: DbSession):
    return ok(
        "Email verified. Your sandbox access is active.",
        participant_auth_service.verify_email(db, payload.unique_id, payload.otp),
    )


@router.post("/resend-otp")
def resend_otp(payload: ResendOtpRequest, db: DbSession):
    return ok(
        "Verification code sent.",
        participant_auth_service.resend_otp(db, payload.unique_id),
    )


@router.post("/registration-state")
def registration_state(payload: ResendOtpRequest, db: DbSession):
    """Reload an interrupted signup so the applicant can finish verifying."""
    return ok(
        "Registration loaded.",
        participant_auth_service.get_registration_state(db, payload.unique_id),
    )


@router.post("/login")
def login(
    payload: ParticipantLoginRequest,
    db: DbSession,
    user_agent: str | None = Header(None),
):
    result = participant_auth_service.login(
        db, payload.email_id, payload.password, user_agent
    )
    return ok(
        "Logged in successfully.",
        result.model_dump(),
        headers={"x-auth-key": result.auth_key},
    )


@router.post("/login/sealed")
def login_sealed(
    payload: SealedPayload, db: DbSession, user_agent: str | None = Header(None)
):
    credentials = rsa_decrypt_payload(payload.post_data)
    result = participant_auth_service.login(
        db,
        credentials.get("email_id") or credentials.get("username", ""),
        credentials.get("password", ""),
        user_agent,
    )
    return ok(
        "Logged in successfully.",
        result.model_dump(),
        headers={"x-auth-key": result.auth_key},
    )


@router.post("/refresh")
def refresh(
    payload: RefreshTokenRequest,
    db: DbSession,
    x_auth_key: str | None = Header(None, alias="x-auth-key"),
):
    """Swap a valid refresh token for a new access token on a live session.

    The access token may already have expired; the refresh token and the
    session handle are what prove the caller.
    """
    data = participant_auth_service.refresh_session(
        db, payload.refresh_token, x_auth_key
    )
    return ok(
        "Session refreshed.",
        {**data, "token_issued_at": data["token_issued_at"].isoformat()},
    )


@router.post("/logout")
def logout(current: CurrentParticipant, db: DbSession):
    participant_auth_service.logout(db, current.auth_key, current.id)
    return ok("Logged out successfully.")


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest, current: CurrentParticipant, db: DbSession
):
    participant_auth_service.change_password(
        db, current.participant, payload.old_password, payload.new_password
    )
    return ok("Password changed successfully.")


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: DbSession):
    participant_auth_service.request_password_reset(db, payload.email_id)
    if settings.fixed_otp:
        return ok(
            "If the account exists, enter the code to set a new password.",
            {"is_fixed_otp": True},
        )
    return ok("If the account exists, a reset link has been sent.", {"is_fixed_otp": False})


@router.post("/reset-password")
def reset_password(payload: ResetPasswordRequest, db: DbSession):
    if payload.token:
        participant_auth_service.reset_password(db, payload.token, payload.new_password)
    else:
        participant_auth_service.reset_password_with_code(
            db, payload.email_id, payload.otp, payload.new_password
        )
    return ok("Password reset successfully. You can now sign in.")
