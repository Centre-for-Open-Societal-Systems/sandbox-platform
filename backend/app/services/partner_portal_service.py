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
    """Make the participant's PM partner match ``active``; record it on ``row``.

    Returns True when the row changed. A PM failure is stored on the row
    (``pm_status`` FAILED, ``pm_error``), never raised: the admin can retry.
    """
    if not pm_enabled() or not row.partner_id:
        return False
    before = (row.pm_status, row.pm_partner_id)
    pm_id = pm.pm_partner_id(row.partner_id)
    try:
        partner = pm.get_partner(pm_id)
        if partner is None:
            if not active:
                # Never onboarded and nothing to give: leave PM alone.
                return False
            request = pm.onboard(
                pm_id,
                row.partner_id,
                name=participant.company_name or participant.display_name,
                org_name=participant.company_name,
                description=(
                    f"OAN sandbox participant {participant.unique_id} ({participant.email_id}), "
                    "onboarded when its access was approved."
                ),
                policies=settings.pm_default_policies,
            )
            pm.approve(request["id"], "Approved in the OAN sandbox.")
            status = IamUserStatus.ACTIVE
        elif partner.get("status") == "created":
            # Onboarded earlier but not approved (e.g. the approval call
            # failed). PM serves nothing for it, so without access it stays so.
            status = IamUserStatus.DISABLED
            if active:
                request = pm.open_onboarding_request(pm_id)
                if request is None:
                    raise AppError(f"PM partner {pm_id} waits for approval but has no open onboarding request.")
                pm.approve(request["id"], "Approved in the OAN sandbox.")
                status = IamUserStatus.ACTIVE
        elif active:
            if partner.get("status") != "active":
                pm.enable(pm_id)
            status = IamUserStatus.ACTIVE
        else:
            if partner.get("status") != "disabled":
                pm.disable(pm_id)
            status = IamUserStatus.DISABLED
        row.pm_partner_id, row.pm_status, row.pm_error = pm_id, str(status), None
    except AppError as exc:
        logger.warning("PM partner for participant %s failed: %s", participant.participant_id, exc.message)
        row.pm_partner_id = row.pm_partner_id or pm_id
        row.pm_status, row.pm_error = str(IamUserStatus.FAILED), exc.message[:2000]
    row.pm_synced_at = datetime.now(UTC)
    return (row.pm_status, row.pm_partner_id) != before or row.pm_status == str(IamUserStatus.FAILED)


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
    }


# ----------------------------------------------------------------------- JWKS
def jwks(db: Session, partner_id: str) -> dict[str, Any]:
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
    key = _jwk(participant.public_key) if participant and participant.public_key else None
    return {"keys": [key] if key else []}


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
