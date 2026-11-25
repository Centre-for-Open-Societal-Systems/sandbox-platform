"""Participants as partners of the OpenG2P Consent Manager partner portal.

An approved participant is one Keycloak user (``iam_user_service``). For the
Consent Manager (CM) partner portal that user also needs, in the CM's partner
realm:

* the attribute ``partner_id`` (the CM's token mapper turns it into the
  ``partner_id`` claim): ``PARTNER_ID_PREFIX`` + participant id, e.g. ``oan-p-42``;
* the portal client's role (``KEYCLOAK_PORTAL_ROLE`` of ``KEYCLOAK_PORTAL_CLIENT_ID``).

And the CM reads what the partner may do from OpenG2P Partner Management (PM),
so the participant is also a PM partner (``PARTNER_OAN_P_42``): onboarded and
approved by the sandbox at the first approval, disabled while the participant
has no access, enabled again when it has. Policies come from
``PM_DEFAULT_POLICIES`` at onboarding; PM staff manage them after that.

PM is told to read the partner's keys from the JWKS this service serves
(``jwks``): the participant's public key, when it has given one.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.logging import get_logger
from app.integrations import partner_management as pm
from app.models.app import ParticipantIamUser
from app.models.enums import IamUserStatus
from app.models.participant import Participant

logger = get_logger(__name__)


def portal_enabled() -> bool:
    return bool(settings.KEYCLOAK_PORTAL_CLIENT_ID)


def pm_enabled() -> bool:
    return pm.is_configured()


def partner_id_for(participant: Participant) -> str:
    return f"{settings.PARTNER_ID_PREFIX}{participant.participant_id}"


# ----------------------------------------------------------- Partner Management
def sync_pm(participant: Participant, row: ParticipantIamUser, active: bool) -> bool:
    """Make the participant's partner in the (UAT) PM match ``active``; record it on ``row``.

    Returns True when the row changed. A PM failure is stored on the row
    (``pm_status`` FAILED, ``pm_error``), never raised: the admin can retry.
    """
    if not pm_enabled() or not row.partner_id:
        return False
    before = (row.pm_status, row.pm_partner_id)
    status, error = _sync_partner(participant, row, active, "PM")
    row.pm_partner_id = row.pm_partner_id or pm.pm_partner_id(row.partner_id)
    row.pm_status, row.pm_error, row.pm_synced_at = status, error, datetime.now(UTC)
    return (row.pm_status, row.pm_partner_id) != before or row.pm_status == str(IamUserStatus.FAILED)


def sync_pm_production(participant: Participant, row: ParticipantIamUser, active: bool) -> bool:
    """The same for production's own PM (PM_PROD_*): ``active`` = production access.

    The partner is onboarded there only once production access is approved, with
    production's JWKS URL; it is disabled there when that access goes. Returns True
    when the row changed."""
    target = pm.production_target()
    if target is None or not pm.is_configured(target) or not row.partner_id:
        return False
    before = row.pm_prod_status
    with pm.use_target(target):
        status, error = _sync_partner(participant, row, active, "PM_PROD")
    row.pm_partner_id = row.pm_partner_id or pm.pm_partner_id(row.partner_id)
    row.pm_prod_status, row.pm_prod_error, row.pm_prod_synced_at = status, error, datetime.now(UTC)
    return row.pm_prod_status != before or row.pm_prod_status == str(IamUserStatus.FAILED)


def _sync_partner(
    participant: Participant, row: ParticipantIamUser, active: bool, which: str
) -> tuple[str | None, str | None]:
    """(status, error) of the participant's partner in the current PM (``pm.use_target``)
    after making it match ``active``.

    Onboarding is a request: with the target's auto-approve the sandbox approves it,
    otherwise it waits for PM's staff (PENDING) and later syncs read the outcome.
    """
    pm_id = pm.pm_partner_id(row.partner_id)
    target = pm.current_target()
    current = row.pm_prod_status if which == "PM_PROD" else row.pm_status
    try:
        caps = pm.profile(target)
        partner = pm.get_partner(pm_id)
        if partner is None:
            if not active:
                # Never onboarded and nothing to give: leave PM alone.
                return current, None
            if not caps.live_jwks and _jwk_of(participant) is None:
                # PM 1.0 copies the keys at onboarding and refuses a partner without one.
                return str(IamUserStatus.NO_KEY), None
            request = pm.onboard(
                pm_id,
                row.partner_id,
                name=participant.company_name or participant.display_name,
                org_name=participant.company_name,
                description=(
                    f"OAN sandbox participant {participant.unique_id} ({participant.email_id}), "
                    f"onboarded when its {'production ' if which == 'PM_PROD' else ''}access was approved."
                ),
                policies=pm.default_policies(),
            )
            if not target.auto_approve:
                return str(IamUserStatus.PENDING), None
            pm.approve(request["id"], "Approved in the OAN sandbox.")
            return str(IamUserStatus.ACTIVE), None
        if partner.get("status") == "created":
            # Onboarded, not approved yet: PM serves nothing for it.
            if not active:
                return str(IamUserStatus.DISABLED), None
            if not target.auto_approve:
                return str(IamUserStatus.PENDING), None
            request = pm.open_onboarding_request(pm_id)
            if request is None:
                raise AppError(f"PM partner {pm_id} waits for approval but has no open onboarding request.")
            pm.approve(request["id"], "Approved in the OAN sandbox.")
            return str(IamUserStatus.ACTIVE), None
        if active:
            if partner.get("status") != "active":
                pm.enable(pm_id)
            if not caps.live_jwks:
                _sync_keys(participant, row, pm_id, target)
            return str(IamUserStatus.ACTIVE), None
        if partner.get("status") != "disabled":
            pm.disable(pm_id)
        return str(IamUserStatus.DISABLED), None
    except AppError as exc:
        logger.warning("%s partner for participant %s failed: %s", which, participant.participant_id, exc.message)
        return str(IamUserStatus.FAILED), exc.message[:2000]


def _jwk_of(participant: Participant) -> dict[str, Any] | None:
    return _jwk(participant.public_key) if participant.public_key else None


def _sync_keys(participant: Participant, row: ParticipantIamUser, pm_id: str, target: pm.Target) -> None:
    """A PM without live JWKS (1.0) keeps copies of the keys: when the partner's key in the
    sandbox is not among them, file a key-update request (add it, revoke the others),
    approved like onboarding (``auto_approve``) or left to PM's staff."""
    jwk = _jwk_of(participant)
    if jwk is None or jwk["kid"] in pm.active_kids(pm_id):
        return
    if pm.open_request(pm_id, "key_update") is not None:
        return  # one key change at a time: PM's staff decide the open one first
    revoke = sorted(pm.active_kids(pm_id) - {jwk["kid"]})
    request = pm.key_update(
        pm_id, row.partner_id,
        f"OAN sandbox participant {participant.unique_id}: signing key changed (new kid {jwk['kid']}).",
        revoke,
    )
    if target.auto_approve:
        pm.approve(request["id"], "Approved in the OAN sandbox.")


def refresh_pending(db: Session) -> int:
    """Read the outcome of onboarding requests waiting for PM's staff (PENDING): an
    approved one turns ACTIVE. Returns how many rows changed. Run periodically."""
    from app.services import iam_user_service

    waiting = (str(IamUserStatus.PENDING), str(IamUserStatus.NO_KEY))
    rows = db.execute(
        select(ParticipantIamUser).where(
            ParticipantIamUser.pm_status.in_(waiting) | ParticipantIamUser.pm_prod_status.in_(waiting)
        )
    ).scalars().all()
    changed = 0
    for row in rows:
        participant = db.get(Participant, row.participant_id)
        if participant is None:
            continue
        roles = iam_user_service.roles_for(participant)
        before = (row.pm_status, row.pm_prod_status)
        if row.pm_status in waiting:
            sync_pm(participant, row, active=bool(roles))
        if row.pm_prod_status in waiting:
            sync_pm_production(participant, row, active="production" in roles)
        if (row.pm_status, row.pm_prod_status) != before:
            changed += 1
    db.commit()
    return changed


def account_out(row: ParticipantIamUser) -> dict[str, Any] | None:
    """The partner portal part of the admin console's Keycloak user view."""
    if not portal_enabled() and not row.partner_id:
        return None
    return {
        "partner_id": row.partner_id,
        "client_id": settings.KEYCLOAK_PORTAL_CLIENT_ID or None,
        "role": settings.KEYCLOAK_PORTAL_ROLE,
        "portal_access": bool(row.portal_access),
        "pm_enabled": pm_enabled(),
        "pm_partner_id": row.pm_partner_id,
        "pm_status": row.pm_status,
        "pm_error": row.pm_error,
        "pm_synced_at": row.pm_synced_at,
        "pm_prod_enabled": pm.production_target() is not None,
        "pm_policies": _policies(row),
        "pm_prod_status": row.pm_prod_status,
        "pm_prod_error": row.pm_prod_error,
        "pm_prod_synced_at": row.pm_prod_synced_at,
    }


# ----------------------------------------------------------------------- JWKS
def jwks(db: Session, partner_id: str, production: bool = False) -> dict[str, Any]:
    """The partner's public keys as a JWKS, for PM (``keys_from_jwks_url``).

    404 for a partner ID the sandbox did not give out or one without access;
    an empty key set while the participant has given no (usable) public key.
    """
    row = db.execute(
        select(ParticipantIamUser).where(ParticipantIamUser.partner_id == partner_id)
    ).scalar_one_or_none()
    if row is None or not row.portal_access:
        raise NotFoundError("Partner not found.")
    participant = db.get(Participant, row.participant_id)
    if production and not (participant and participant.is_prod_approved and participant.is_prod_enabled):
        # Production's PM reads only partners that have production access.
        raise NotFoundError("Partner not found.")
    key = _jwk(participant.public_key) if participant and participant.public_key else None
    return {"keys": [key] if key else []}


def public_jwk(pem: str) -> dict[str, Any] | None:
    """``_jwk`` for other services (production app clients' private_key_jwt)."""
    return _jwk(pem)


def _jwk(pem: str) -> dict[str, Any] | None:
    """A PEM public key as a JWK with ``kid`` (RFC 7638 thumbprint) and ``alg``;
    None when it is not a public key PM would accept."""
    try:
        key = serialization.load_pem_public_key(pem.strip().encode())
    except (ValueError, TypeError):
        logger.info("Participant public key is not a PEM public key; JWKS left empty")
        return None
    if isinstance(key, rsa.RSAPublicKey):
        if key.key_size < 2048:
            return None
        jwk, alg, members = jwt.algorithms.RSAAlgorithm.to_jwk(key, as_dict=True), "RS256", ("e", "kty", "n")
    elif isinstance(key, ec.EllipticCurvePublicKey):
        alg = {"secp256r1": "ES256", "secp384r1": "ES384"}.get(key.curve.name)
        if alg is None:
            return None
        jwk, members = jwt.algorithms.ECAlgorithm.to_jwk(key, as_dict=True), ("crv", "kty", "x", "y")
    elif isinstance(key, ed25519.Ed25519PublicKey):
        jwk, alg, members = jwt.algorithms.OKPAlgorithm.to_jwk(key, as_dict=True), "EdDSA", ("crv", "kty", "x")
    else:
        return None
    canonical = json.dumps({m: jwk[m] for m in members}, separators=(",", ":"), sort_keys=True)
    kid = base64.urlsafe_b64encode(hashlib.sha256(canonical.encode()).digest()).rstrip(b"=").decode()
    return {**{m: jwk[m] for m in members}, "kid": kid, "alg": alg, "use": "sig"}


def _policies(row: ParticipantIamUser) -> list[dict[str, Any]]:
    """The PM policies the sandbox asked for (``pm_policy_service``), for the console."""
    from sqlalchemy.orm import object_session

    from app.services import pm_policy_service

    db = object_session(row)
    return pm_policy_service.rows_out(db, row.participant_id) if db is not None else []
