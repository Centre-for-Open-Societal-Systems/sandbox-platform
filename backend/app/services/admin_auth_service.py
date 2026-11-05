"""Admin authentication: sign-in, sign-out, password lifecycle."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.context import client_ip_ctx
from app.core.exceptions import NotFoundError, UnauthorizedError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_token_urlsafe,
    hash_password,
    sha256_token,
    verify_password,
    verify_password_or_dummy,
)
from app.models.admin import AdmUser
from app.repositories.admin_repository import (
    AdminTokenRepository,
    AdminUserRepository,
    PermissionRepository,
    RoleRepository,
)
from app.schemas.admin import AdminLoginResponse
from app.services import audit_service, auth_throttle_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_templated

INVALID_CREDENTIALS = "No such username or password."
RESET_TOKEN_TTL_HOURS = 24


def login(
    db: Session, username: str, password: str, user_agent: str | None = None
) -> AdminLoginResponse:
    auth_throttle_service.limit_ip(db, "admin-login")
    throttle_key = f"login:admin:{(username or '').strip().lower()}"
    auth_throttle_service.assert_not_locked(db, throttle_key)

    users = AdminUserRepository(db)
    user = users.get_by_login(username)

    # The same message (and the same bcrypt cost) for "no such user" and
    # "wrong password" so the endpoint cannot be used to enumerate accounts.
    if not verify_password_or_dummy(password, user.login_pass if user else None):
        auth_throttle_service.record_failure(db, throttle_key)
        audit_service.record(
            db,
            Action.ADMIN_LOGIN_FAILED,
            actor_type="admin",
            actor_name=username,
            description="Failed sign-in attempt",
        )
        raise UnauthorizedError(INVALID_CREDENTIALS)
    auth_throttle_service.clear(db, throttle_key)

    if not user.is_master and not user.is_enabled:
        raise UnauthorizedError(
            "Your account has been blocked, contact the system administrator."
        )

    token = AdminTokenRepository(db).create(
        admin_id=user.admin_id,
        ip_address=client_ip_ctx.get() or None,
        user_agent=user_agent,
    )

    permissions = PermissionRepository(db).permission_flags(
        user.role_id, user.is_master
    )
    role = RoleRepository(db).get(user.role_id) if user.role_id else None

    audit_service.record(
        db,
        Action.ADMIN_LOGIN,
        actor_type="admin",
        actor_id=user.admin_id,
        actor_name=user.full_name or user.login_name,
        country_code=user.country_code,
        user_agent=user_agent,
    )

    return AdminLoginResponse(
        first_name=user.first_name,
        last_name=user.last_name,
        email_id=user.email_id,
        mobile_no=user.mobile_no,
        is_master=user.is_master,
        role=role.role_name if role else "",
        country_code=user.country_code,
        admin_area_code=user.admin_area_code,
        access_token=create_access_token(user.admin_id, {"role": "admin"}),
        refresh_token=create_refresh_token(user.admin_id, {"role": "admin"}),
        token_expiry=settings.JWT_ACCESS_TOKEN_EXPIRES,
        token_issued_at=datetime.now(UTC),
        auth_key=token.unique_id,
        permissions=permissions,
    )


def logout(db: Session, auth_key: str, admin_id: int) -> None:
    tokens = AdminTokenRepository(db)
    token = tokens.get_active(auth_key)
    if token is not None:
        tokens.logout(token)
    audit_service.record(db, Action.ADMIN_LOGOUT, actor_type="admin", actor_id=admin_id)


def change_password(
    db: Session, user: AdmUser, old_password: str, new_password: str
) -> None:
    if not verify_password(old_password, user.login_pass):
        raise ValidationError("Current password is incorrect.")
    if verify_password(new_password, user.login_pass):
        raise ValidationError(
            "New password must be different from the current password."
        )

    user.login_pass = hash_password(new_password)
    user.modify_by = user.admin_id
    db.commit()

    # Force other devices to re-authenticate with the new credentials.
    AdminTokenRepository(db).logout_all(user.admin_id)

    audit_service.record(
        db,
        Action.ADMIN_PASSWORD_CHANGE,
        actor_type="admin",
        actor_id=user.admin_id,
        actor_name=user.full_name or user.login_name,
    )


def request_password_reset(db: Session, email_id: str) -> None:
    """Issue a reset link.

    Always succeeds from the caller's point of view - revealing whether an
    address is registered would leak account existence.
    """
    auth_throttle_service.limit_ip(db, "admin-forgot")
    user = AdminUserRepository(db).get_by(email_id=email_id.strip().lower())
    if user is None:
        return

    token = generate_token_urlsafe()
    # Only the hash is stored; the link in the mail carries the token itself.
    user.set_pass_token = sha256_token(token)
    user.set_pass_token_time = datetime.now(UTC)
    db.commit()

    send_templated(
        db,
        TemplateCode.ADMIN_RESET_PASSWORD,
        user.email_id,
        {"name": user.full_name or user.login_name, "token": token},
    )


def set_password(db: Session, token: str, new_password: str) -> None:
    auth_throttle_service.limit_ip(db, "admin-set-password")
    users = AdminUserRepository(db)
    user = users.get_by_set_pass_token(token)
    if user is None:
        raise NotFoundError("This link is not valid.")

    if _token_expired(user.set_pass_token_time):
        raise ValidationError("This link has expired, please request a new one.")

    user.login_pass = hash_password(new_password)
    user.set_pass_token = None
    user.set_pass_token_time = None
    user.is_activated = True
    user.activate_date = datetime.now(UTC)
    db.commit()
    # Whoever held a session before the reset is signed out.
    AdminTokenRepository(db).logout_all(user.admin_id)


def _token_expired(issued_at: datetime | None) -> bool:
    if issued_at is None:
        return True
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - issued_at > timedelta(hours=RESET_TOKEN_TTL_HOURS)
