"""Audit trail writer.

Every state-changing admin action funnels through ``record`` so User Tracking
shows a complete history. Failures here are swallowed - a broken audit write
must never take down the action it was describing.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.context import client_ip_ctx, current_correlation_id
from app.core.logging import get_logger
from app.repositories.log_repository import UserActionLogRepository

logger = get_logger(__name__)


class Action:
    """Canonical action verbs, so the audit filter has a stable vocabulary."""

    ADMIN_LOGIN = "ADMIN_LOGIN"
    ADMIN_LOGIN_FAILED = "ADMIN_LOGIN_FAILED"
    ADMIN_LOGOUT = "ADMIN_LOGOUT"
    ADMIN_PASSWORD_CHANGE = "ADMIN_PASSWORD_CHANGE"

    ADMIN_USER_CREATE = "ADMIN_USER_CREATE"
    ADMIN_USER_UPDATE = "ADMIN_USER_UPDATE"
    ADMIN_USER_DELETE = "ADMIN_USER_DELETE"
    ADMIN_USER_TOGGLE = "ADMIN_USER_TOGGLE"
    ADMIN_USER_INVITE = "ADMIN_USER_INVITE"

    ROLE_CREATE = "ROLE_CREATE"
    ROLE_UPDATE = "ROLE_UPDATE"
    ROLE_DELETE = "ROLE_DELETE"
    ROLE_TOGGLE = "ROLE_TOGGLE"
    PERMISSION_UPDATE = "PERMISSION_UPDATE"

    PARTICIPANT_SIGNUP = "PARTICIPANT_SIGNUP"
    PARTICIPANT_VERIFY_EMAIL = "PARTICIPANT_VERIFY_EMAIL"
    PARTICIPANT_LOGIN = "PARTICIPANT_LOGIN"
    PARTICIPANT_LOGOUT = "PARTICIPANT_LOGOUT"
    PARTICIPANT_APPROVE = "PARTICIPANT_APPROVE"
    PARTICIPANT_REJECT = "PARTICIPANT_REJECT"
    PARTICIPANT_TOGGLE = "PARTICIPANT_TOGGLE"
    PARTICIPANT_DELETE = "PARTICIPANT_DELETE"
    PARTICIPANT_PROFILE_UPDATE = "PARTICIPANT_PROFILE_UPDATE"
    PROMOTION_REQUEST = "PROMOTION_REQUEST"
    PROMOTION_DECISION = "PROMOTION_DECISION"

    PRODUCT_CREATE = "PRODUCT_CREATE"
    PRODUCT_UPDATE = "PRODUCT_UPDATE"
    PRODUCT_DELETE = "PRODUCT_DELETE"
    PRODUCT_PUBLISH = "PRODUCT_PUBLISH"
    SPEC_IMPORT = "SPEC_IMPORT"

    ENDPOINT_CREATE = "ENDPOINT_CREATE"
    ENDPOINT_UPDATE = "ENDPOINT_UPDATE"
    ENDPOINT_DELETE = "ENDPOINT_DELETE"
    ENDPOINT_PUBLISH = "ENDPOINT_PUBLISH"
    SCHEMA_UPSERT = "SCHEMA_UPSERT"

    MASTER_CREATE = "MASTER_CREATE"
    MASTER_UPDATE = "MASTER_UPDATE"
    MASTER_DELETE = "MASTER_DELETE"
    MASTER_TOGGLE = "MASTER_TOGGLE"

    CONTENT_UPSERT = "CONTENT_UPSERT"
    CONTENT_DELETE = "CONTENT_DELETE"

    SANDBOX_CALL = "SANDBOX_CALL"

    EXPORT = "EXPORT"


def record(
    db: Session,
    action: str,
    *,
    actor_type: str = "system",
    actor_id: str | int | None = None,
    actor_name: str | None = None,
    entity: str | None = None,
    entity_id: str | int | None = None,
    description: str | None = None,
    changes: dict[str, Any] | None = None,
    country_code: str | None = None,
    user_agent: str | None = None,
) -> None:
    try:
        UserActionLogRepository(db).record(
            actor_type=actor_type,
            actor_id=str(actor_id) if actor_id is not None else None,
            actor_name=actor_name,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            description=description,
            changes=changes,
            country_code=country_code,
            correlation_id=current_correlation_id() or None,
            ip_address=client_ip_ctx.get() or None,
            user_agent=user_agent,
        )
    except Exception as exc:  # pragma: no cover - audit must never break flow
        logger.error("Failed to write audit entry %s: %s", action, exc)
        db.rollback()


def record_admin(db: Session, admin, action: str, **kwargs: Any) -> None:
    """Convenience wrapper that fills the actor fields from an AdminPrincipal."""
    record(
        db,
        action,
        actor_type="admin",
        actor_id=admin.id,
        actor_name=admin.user.full_name or admin.user.login_name,
        country_code=kwargs.pop("country_code", admin.country_code),
        **kwargs,
    )


def record_participant(db: Session, principal, action: str, **kwargs: Any) -> None:
    """Convenience wrapper that fills the actor fields from a ParticipantPrincipal."""
    record(
        db,
        action,
        actor_type="participant",
        actor_id=principal.id,
        actor_name=principal.participant.display_name,
        country_code=kwargs.pop("country_code", principal.country_code),
        **kwargs,
    )
