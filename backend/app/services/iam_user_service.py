"""Participants' users in Keycloak.

Every participant is one Keycloak user in ``KEYCLOAK_REALM`` (username = the
email address, same password as the portal). Access is a client role of the
shared client ``KEYCLOAK_PARTNER_CLIENT_ID``: one role per approved
environment (``uat``, ``production``). Partners ask that client for a token
with the password grant; the token lists the roles and carries
``participant_uid``.

The user is created when an administrator first approves an environment (UAT
approval, i.e. the account approval), never at sign-up: a registration that
is still waiting, or was rejected, leaves nothing in Keycloak.

``sync`` makes Keycloak match the participant: the user is enabled only while
the participant may use at least one environment (so a rejected, disabled or
deleted participant cannot get a token), and holds exactly the roles of the
approved environments. Approve / reject, enable / disable, delete and
password changes all call it.

The password reaches Keycloak only where the sandbox sees it in clear:
sign-in, change and reset. The sandbox stores only a hash, so the user made
at approval has no password until the participant's next portal sign-in sets
it (the same for a user made by an admin retry).

Nothing here raises into the portal flows: a Keycloak failure is stored on
the row (status FAILED, ``error``) and an administrator can retry it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.context import assert_in_admin_scope
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.integrations import keycloak
from app.models.app import ParticipantIamUser
from app.models.enums import ActivationStatus, Environment, IamUserStatus
from app.models.participant import Participant
from app.services import audit_service, partner_portal_service
from app.services.audit_service import Action

logger = get_logger(__name__)


def is_enabled() -> bool:
    return keycloak.is_configured()


def is_approved(participant: Participant, environment: Environment) -> bool:
    return {
        Environment.UAT: participant.is_uat_approved,
        Environment.PRODUCTION: participant.is_prod_approved and participant.is_prod_enabled,
    }.get(environment, False)


def roles_for(participant: Participant) -> set[str]:
    """Environment roles the participant should hold right now."""
    if (
        participant.is_deleted
        or not participant.is_enabled
        or participant.is_activated == int(ActivationStatus.BLOCKED)
    ):
        return set()
    return {
        str(env).lower()
        for env in Environment
        if str(env) in settings.keycloak_environment_set and is_approved(participant, env)
    }


# ---------------------------------------------------------------- lifecycle
def sync(
    db: Session,
    participant: Participant,
    *,
    password: str | None = None,
    actor_id: int | None = None,
    include_pm: bool = True,
) -> ParticipantIamUser | None:
    """Create or update the participant's user, its roles and (when given) its
    password; then (``include_pm``) its partner in Partner Management."""
    if not is_enabled():
        return None
    row = _row(db, participant.participant_id)
    roles = roles_for(participant)
    if row is None and not roles:
        # Nothing approved yet (sign-up, verification, a rejected sign-up):
        # no Keycloak user until an administrator approves UAT access.
        return None
    if row is None:
        row = ParticipantIamUser(
            participant_id=participant.participant_id,
            realm=settings.KEYCLOAK_REALM,
            username=participant.email_id.lower(),
            roles="",
            status=str(IamUserStatus.FAILED),
            added_by=actor_id,
        )
        db.add(row)
        db.flush()
    before = (row.status, row.roles, row.portal_access)

    enabled = bool(roles)
    attributes = {"participant_uid": str(participant.unique_id)}
    if partner_portal_service.portal_enabled():
        # The Consent Manager partner portal: partner_id claim + portal role.
        row.partner_id = row.partner_id or partner_portal_service.partner_id_for(participant)
        attributes[settings.KEYCLOAK_PARTNER_ID_ATTRIBUTE] = row.partner_id
    profile = {
        "email": participant.email_id.lower(),
        "first_name": participant.first_name or "",
        "last_name": participant.last_name or "",
        "enabled": enabled,
        "email_verified": bool(participant.is_email_verified),
        "attributes": attributes,
    }
    try:
        user_id = row.keycloak_id or keycloak.find_user(row.username)
        if user_id is None:
            user_id = keycloak.create_user(row.username, password=password, **profile)
        else:
            keycloak.update_user(user_id, **profile)
            if password:
                keycloak.set_password(user_id, password)
        keycloak.set_environment_roles(user_id, roles)
        if not enabled and row.status == str(IamUserStatus.ACTIVE):
            # Access taken away: its Keycloak sessions end too, so no refresh
            # token of an earlier sign-in still works.
            keycloak.logout_user(user_id)
        row.keycloak_id = user_id
        if partner_portal_service.portal_enabled():
            keycloak.set_portal_role(user_id, enabled)
            row.portal_access = enabled
        if password:
            row.password_synced_at = datetime.now(UTC)
        row.roles = ",".join(sorted(roles))
        row.status, row.error = str(IamUserStatus.ACTIVE if enabled else IamUserStatus.DISABLED), None
    except AppError as exc:
        logger.warning("Keycloak user for participant %s failed: %s", participant.participant_id, exc.message)
        row.status, row.error = str(IamUserStatus.FAILED), exc.message[:2000]
    pm_changed = include_pm and partner_portal_service.sync_pm(participant, row, active=enabled)
    row.synced_at = datetime.now(UTC)
    row.modify_by = actor_id
    db.commit()

    if (row.status, row.roles, row.portal_access) != before or row.status == str(IamUserStatus.FAILED):
        audit_service.record(
            db,
            Action.IAM_USER_FAILED if row.status == str(IamUserStatus.FAILED) else Action.IAM_USER_SYNC,
            entity="participant_iam_user",
            entity_id=row.id,
            description=f"Keycloak user {row.username}: {row.status}, roles [{row.roles}]"
            + (f", partner portal {'on' if row.portal_access else 'off'}" if row.partner_id else "")
            + (f" ({row.error})" if row.error else ""),
            country_code=participant.country_code,
        )
    if pm_changed:
        audit_service.record(
            db,
            Action.PM_PARTNER_FAILED if row.pm_status == str(IamUserStatus.FAILED) else Action.PM_PARTNER_SYNC,
            entity="participant_iam_user",
            entity_id=row.id,
            description=f"Partner Management partner {row.pm_partner_id}: {row.pm_status}"
            + (f" ({row.pm_error})" if row.pm_error else ""),
            country_code=participant.country_code,
        )
    return row


def password_changed(db: Session, participant: Participant, password: str) -> None:
    """The portal password changed (change, reset): Keycloak gets it too."""
    sync(db, participant, password=password, include_pm=False)


def signed_in(db: Session, participant: Participant, password: str) -> None:
    """Portal sign-in: give Keycloak the password if it does not have it yet."""
    if not is_enabled():
        return
    row = _row(db, participant.participant_id)
    if row is None or row.password_synced_at is None or row.status == str(IamUserStatus.FAILED):
        sync(db, participant, password=password, include_pm=False)


def needs_password(db: Session, participant: Participant) -> bool:
    """True while Keycloak does not hold the participant's password yet (no
    user, never synced, or the last sync failed): the sandbox's own hash is
    then the only check there is."""
    row = _row(db, participant.participant_id)
    return row is None or row.password_synced_at is None or row.status == str(IamUserStatus.FAILED)


# ------------------------------------------------------------- participant
# -------------------------------------------------------------------- admin
def admin_account(db: Session, participant_id: int) -> dict[str, Any]:
    participant = db.get(Participant, participant_id)
    if participant is None or not assert_in_admin_scope(participant.country_code):
        raise NotFoundError("Participant not found.")
    row = _row(db, participant_id)
    return {"enabled": is_enabled(), "account": account_out(row) if row else None}


def retry(db: Session, admin, participant_id: int) -> dict[str, Any]:
    if not is_enabled():
        raise ValidationError("Keycloak provisioning is switched off (KEYCLOAK_PROVISIONING_ENABLED).")
    participant = db.get(Participant, participant_id)
    if participant is None or not assert_in_admin_scope(participant.country_code):
        raise NotFoundError("Participant not found.")
    if _row(db, participant_id) is None and not roles_for(participant):
        raise ValidationError(
            "No environment is approved yet: the Keycloak user is created when UAT access is approved."
        )
    row = sync(db, participant, actor_id=admin.id)
    audit_service.record_admin(
        db, admin, Action.IAM_USER_RETRY, entity="participant", entity_id=participant_id,
        description=f"Re-ran Keycloak sync: {row.status if row else 'skipped'}",
    )
    return admin_account(db, participant_id)


# ------------------------------------------------------------------ helpers
def account_out(row: ParticipantIamUser) -> dict[str, Any]:
    """The participant's Keycloak user as the admin console shows it.

    Participants are not shown it: the gateway does not accept Keycloak tokens
    yet (APIs open with the app API key), so a token would only confuse them.
    """
    return {
        "realm": row.realm,
        "username": row.username,
        "client_id": settings.KEYCLOAK_PARTNER_CLIENT_ID,
        "token_url": keycloak.token_url(),
        "grant_type": "password",
        "roles": [role for role in row.roles.split(",") if role],
        "status": row.status,
        "password_synced": row.password_synced_at is not None,
        "added_date": row.added_date,
        "synced_at": row.synced_at,
        "error": row.error,
        "keycloak_id": row.keycloak_id,
        "console_url": keycloak.console_url(row.keycloak_id) if row.keycloak_id else None,
        "partner_portal": partner_portal_service.account_out(row),
    }


def _row(db: Session, participant_id: int) -> ParticipantIamUser | None:
    return db.execute(
        select(ParticipantIamUser).where(ParticipantIamUser.participant_id == participant_id)
    ).scalar_one_or_none()
