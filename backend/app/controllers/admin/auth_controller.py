"""Admin authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Header

from app.config.settings import settings
from app.core.deps import CurrentAdmin, DbSession
from app.core.responses import ok
from app.core.security import rsa_decrypt_payload
from app.schemas.admin import (
    AdminLoginRequest,
    ChangePasswordRequest,
    CheckUsernameRequest,
    ForgotPasswordRequest,
    SetPasswordRequest,
)
from app.schemas.common import SealedPayload
from app.services import admin_auth_service, admin_user_service, log_service

router = APIRouter(prefix="/auth", tags=["Admin / Auth"])


@router.post("/login")
def login(
    payload: AdminLoginRequest, db: DbSession, user_agent: str | None = Header(None)
):
    result = admin_auth_service.login(
        db, payload.username, payload.password, user_agent
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
    """Sign-in with an RSA-sealed credential envelope."""
    credentials = rsa_decrypt_payload(payload.post_data)
    result = admin_auth_service.login(
        db,
        credentials.get("username", ""),
        credentials.get("password", ""),
        user_agent,
    )
    return ok(
        "Logged in successfully.",
        result.model_dump(),
        headers={"x-auth-key": result.auth_key},
    )


@router.post("/logout")
def logout(admin: CurrentAdmin, db: DbSession):
    admin_auth_service.logout(db, admin.auth_key, admin.id)
    return ok("Logged out successfully.")


@router.get("/profile")
def profile(admin: CurrentAdmin, db: DbSession):
    return ok(
        "Profile loaded.",
        admin_user_service.get_user(db, admin.id).model_dump(),
    )


@router.get("/dashboard")
def dashboard(admin: CurrentAdmin, db: DbSession):
    data = log_service.dashboard(db, admin.country_code)
    return ok("Dashboard loaded.", data.model_dump())


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, admin: CurrentAdmin, db: DbSession):
    admin_auth_service.change_password(
        db, admin.user, payload.old_password, payload.new_password
    )
    return ok("Password changed successfully. Please sign in again.")


@router.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest, db: DbSession):
    admin_auth_service.request_password_reset(db, payload.email_id)
    # Deliberately unconditional so the response cannot confirm registration.
    if settings.fixed_otp:
        return ok(
            "If the address is registered, enter the code to set a new password.",
            {"is_fixed_otp": True},
        )
    return ok(
        "If the address is registered, a reset link has been sent.", {"is_fixed_otp": False}
    )


@router.post("/set-password")
def set_password(payload: SetPasswordRequest, db: DbSession):
    if payload.token:
        admin_auth_service.set_password(db, payload.token, payload.new_password)
    else:
        admin_auth_service.set_password_with_code(
            db, payload.email_id, payload.otp, payload.new_password
        )
    return ok("Password set successfully. You can now sign in.")


@router.post("/check-username")
def check_username(payload: CheckUsernameRequest, admin: CurrentAdmin, db: DbSession):
    available = admin_user_service.is_login_available(
        db, payload.login_name, payload.exclude_admin_id
    )
    return ok(
        "Username is available." if available else "Username is already taken.",
        {"available": available},
    )
