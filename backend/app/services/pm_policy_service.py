"""Data policies the sandbox asks for on a partner's behalf (D3).

An API product may carry a data policy (``ApiProduct.pm_policy``, in OpenG2P PM's
PolicyInput shape): what data a partner holding the product may request from a
registry (``data_controller`` + ``allowed_data_scopes``) or which exchange use case it
may run (``use_case``). The gateway decides which APIs an app may call; the policy
decides what data the partner may ask for, and that decision belongs to the data
side's staff. So the sandbox **files** policies and reads the outcome; it approves
only where its settings allow (UAT PM, ``PM_AUTO_APPROVE``).

Where a policy is filed is a **backend** per environment (``POLICY_BACKEND``):

* ``pm`` - OpenG2P Partner Management policy requests (a PM release with policies,
  ``openg2p_contract.PM_PROFILES``). One request per change; PM's staff approve.
* ``cm`` - the COSS Consent Manager, where COSS keeps policies today: one binding per
  (partner audience, registry) with a versioned policy; a widening waits for AWE's
  approvers, a narrowing applies at once, a dropped policy suspends the binding.
  Registry policies only (no use cases).
* ``auto`` - ``pm`` when that environment's PM has policies, else ``cm`` when its CM
  is configured. When COSS moves to the new PM, only the settings change.

``sync_participant`` reconciles, per environment, what the participant's active apps'
approved products ask for with what the sandbox filed before (``ParticipantPmPolicy``):
open requests are read first; nothing is filed while the partner is not ready there
(WAITING); new or changed policies are filed, dropped ones revoked; a rejected one is
filed again only when the products ask for something else. Products asking for the
same key are merged (lists united, the partner-consent flag if any asks for it);
an empty ``allowed_signing_algs`` becomes the algorithm of the partner's key.
Policies staff made themselves are never touched. Nothing here raises: failures are
stored on the rows (FAILED) and retried by ``refresh_pending``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.integrations import consent_manager_admin as cm
from app.integrations import partner_management as pm
from app.models.app import (
    ApiProduct,
    ParticipantApp,
    ParticipantAppProduct,
    ParticipantIamUser,
    ParticipantPmPolicy,
)
from app.models.enums import (
    AppStatus,
    Environment,
    IamUserStatus,
    PmPolicyStatus,
    SubscriptionStatus,
)
from app.models.participant import Participant
from app.services import audit_service
from app.services.audit_service import Action

logger = get_logger(__name__)

_LISTS = ("allowed_data_scopes", "allowed_purposes", "allowed_subject_id_types", "allowed_signing_algs")
_OPEN = (str(PmPolicyStatus.PENDING), str(PmPolicyStatus.REVOKING))
UAT, PRODUCTION = "UAT", "PRODUCTION"


def policy_key(policy: dict[str, Any]) -> str:
    if policy.get("data_controller"):
        return f"data_controller:{policy['data_controller']}"
    return f"use_case:{policy['use_case']}"


def _ref(key: str) -> dict[str, str]:
    kind, _, value = key.partition(":")
    return {kind: value}


def _same(a: dict | None, b: dict | None) -> bool:
    return json.dumps(a or {}, sort_keys=True) == json.dumps(b or {}, sort_keys=True)


# ------------------------------------------------------------------ backends
@dataclass(frozen=True, slots=True)
class Backend:
    """Where one environment's policies are filed."""

    kind: str  # "pm" | "cm"
    environment: str  # "UAT" | "PRODUCTION"
    pm_target: pm.Target | None = None
    cm_target: cm.Target | None = None


def _pm_target(env: str) -> pm.Target | None:
    target = pm.production_target() if env == PRODUCTION else pm.main_target()
    return target if target is not None and pm.is_configured(target) else None


def _cm_target(env: str) -> cm.Target | None:
    target = cm.production_target() if env == PRODUCTION else cm.main_target()
    return target if cm.is_configured(target) else None


def backend_for(env: str) -> Backend | None:
    """The backend of one environment (``POLICY_BACKEND``); None = policies go nowhere.
    ``auto`` needs to know the PM's release: when PM cannot be reached to tell, nothing
    is chosen this time (rather than filing in the wrong place)."""
    choice = settings.POLICY_BACKEND
    if choice == "none":
        return None
    pm_target, cm_target = _pm_target(env), _cm_target(env)
    if choice in ("pm", "auto") and pm_target is not None:
        try:
            has_policies = pm.profile(pm_target).policies
        except AppError as exc:
            logger.warning("Policy backend of %s undecided: %s", env, exc.message)
            return None
        if has_policies:
            return Backend("pm", env, pm_target=pm_target)
    if choice in ("cm", "auto") and cm_target is not None:
        return Backend("cm", env, pm_target=pm_target, cm_target=cm_target)
    return None


def backends() -> list[Backend]:
    """One per environment with a policy backend; production's only when it has its own
    PM or CM (else production apps' policies go to UAT's)."""
    found = []
    for env in (UAT, PRODUCTION):
        if env == PRODUCTION and _pm_target(PRODUCTION) is None and _cm_target(PRODUCTION) is None:
            continue
        backend = backend_for(env)
        if backend is not None:
            found.append(backend)
    return found


def _environment_of(app_environment: str) -> str:
    """The policy environment holding an app's environment."""
    prod = _pm_target(PRODUCTION) is not None or _cm_target(PRODUCTION) is not None
    return PRODUCTION if str(app_environment).upper() == str(Environment.PRODUCTION) and prod else UAT


# --------------------------------------------------------------- what is asked
def desired(db: Session, participant: Participant, environment: str) -> dict[str, tuple[dict, list[str]]]:
    """``policy key -> (merged policy, product names)`` the participant's active apps in
    ``environment`` ask for through their approved products."""
    from app.services.app_gateway_service import owner_active

    rows = db.execute(
        select(ParticipantApp, ApiProduct)
        .join(ParticipantAppProduct, ParticipantAppProduct.app_id == ParticipantApp.app_id)
        .join(ApiProduct, ApiProduct.api_product_id == ParticipantAppProduct.api_product_id)
        .where(
            ParticipantApp.participant_id == participant.participant_id,
            ParticipantApp.is_deleted.is_(False),
            ParticipantApp.status == int(AppStatus.ACTIVE),
            ParticipantAppProduct.status == int(SubscriptionStatus.APPROVED),
            ApiProduct.is_deleted.is_(False),
            ApiProduct.pm_policy.is_not(None),
        )
        .order_by(ApiProduct.api_product_id)
    ).all()
    merged: dict[str, tuple[dict, list[str]]] = {}
    for app, product in rows:
        if _environment_of(app.environment) != environment or not owner_active(participant, app.environment):
            continue
        policy = dict(product.pm_policy or {})
        if not (policy.get("data_controller") or policy.get("use_case")):
            continue
        key = policy_key(policy)
        name = product.display_name or product.name
        if key not in merged:
            merged[key] = (policy, [name])
            continue
        current, names = merged[key]
        for field in _LISTS:
            values = list(current.get(field) or [])
            values += [v for v in policy.get(field) or [] if v not in values]
            if values:
                current[field] = values
        if policy.get("allow_partner_consents"):
            current["allow_partner_consents"] = True
        if name not in names:
            names.append(name)
    algs = _key_algorithms(participant)
    for policy, _ in merged.values():
        if not policy.get("allowed_signing_algs") and algs:
            policy["allowed_signing_algs"] = algs
    return merged


def _key_algorithms(participant: Participant) -> list[str]:
    from app.services.partner_portal_service import public_jwk

    jwk = public_jwk(participant.public_key) if participant.public_key else None
    return [jwk["alg"]] if jwk else []


# ------------------------------------------------------------------ reconcile
def sync_participant(db: Session, participant_id: int) -> bool:
    """Reconcile the participant's policies in every environment. Never raises; True
    when a row changed."""
    found = backends()
    if not found:
        return False
    participant = db.get(Participant, participant_id)
    iam = db.execute(
        select(ParticipantIamUser).where(ParticipantIamUser.participant_id == participant_id)
    ).scalar_one_or_none()
    if participant is None or iam is None or not iam.partner_id:
        return False
    changed = False
    for backend in found:
        try:
            changed |= _reconcile(db, participant, iam, backend)
        except Exception as exc:  # noqa: BLE001 - a policy sync must never break the caller
            logger.error("Policy sync of participant %s (%s %s) failed: %s",
                         participant_id, backend.kind, backend.environment, exc)
            db.rollback()
    return changed


def _reconcile(db: Session, participant: Participant, iam: ParticipantIamUser, backend: Backend) -> bool:
    impl = _PmBackend(backend, participant, iam) if backend.kind == "pm" else _CmBackend(backend, participant, iam)
    env, now = backend.environment, datetime.now(UTC)
    rows = {
        r.policy_key: r
        for r in db.execute(
            select(ParticipantPmPolicy).where(
                ParticipantPmPolicy.participant_id == participant.participant_id,
                ParticipantPmPolicy.environment == env,
                ParticipantPmPolicy.backend == backend.kind,
            )
        ).scalars()
    }
    before = {k: (r.status, r.request_id) for k, r in rows.items()}
    events: list[str] = []

    # 1. The decisions on open requests.
    for key, row in list(rows.items()):
        if row.status in _OPEN and row.request_id:
            event = impl.poll(row)
            if event:
                events.append(f"{key} {event}")
                if event == "revoked":
                    db.delete(row)
                    rows.pop(key)
            row.synced_at = now

    wanted = desired(db, participant, env)
    ready = impl.ready()

    # 2. Rows nothing asks for any more.
    to_revoke: list[ParticipantPmPolicy] = []
    for key, row in list(rows.items()):
        if key in wanted:
            continue
        if row.status == str(PmPolicyStatus.ACTIVE) and ready:
            to_revoke.append(row)
        elif row.status in (str(PmPolicyStatus.WAITING), str(PmPolicyStatus.REJECTED), str(PmPolicyStatus.FAILED)):
            db.delete(row)
            rows.pop(key)
        # PENDING: revoked once it is decided; ACTIVE while not ready: revoked later.

    # 3. What to file.
    to_file: list[tuple[ParticipantPmPolicy, dict, list[str]]] = []
    for key, (policy, names) in wanted.items():
        row = rows.get(key)
        if row is None:
            row = ParticipantPmPolicy(participant_id=participant.participant_id, environment=env,
                                      backend=backend.kind, policy_key=key,
                                      status=str(PmPolicyStatus.WAITING), products=names)
            db.add(row)
            rows[key] = row
        row.products = names
        if row.status in _OPEN:
            continue  # one open request per policy
        unsupported = impl.unsupported(policy)
        if unsupported:
            row.status, row.error = str(PmPolicyStatus.REJECTED), unsupported
            continue
        if not ready:
            if row.status != str(PmPolicyStatus.ACTIVE):
                row.status, row.error = str(PmPolicyStatus.WAITING), None
            continue
        if row.status in (str(PmPolicyStatus.ACTIVE), str(PmPolicyStatus.REJECTED)) and _same(row.policy, policy):
            continue
        to_file.append((row, policy, names))

    if to_file or to_revoke:
        events += impl.apply(to_file, to_revoke, now)
        for row in to_revoke:
            if row.status == "_revoked":
                db.delete(row)
                rows.pop(row.policy_key, None)

    db.commit()
    after = {k: (r.status, r.request_id) for k, r in rows.items()}
    if events:
        where = {"pm": "Partner Management", "cm": "Consent Manager"}[backend.kind]
        audit_service.record(
            db, Action.PM_PARTNER_SYNC, entity="participant_pm_policy", entity_id=participant.participant_id,
            description=f"{'Production ' if env == PRODUCTION else ''}{where} policies of {iam.partner_id}: "
            + "; ".join(events),
            country_code=participant.country_code,
        )
    return after != before


def _description(participant: Participant, env: str, to_file, to_revoke) -> str:
    parts = []
    if to_file:
        parts.append("asks for " + ", ".join(
            f"{row.policy_key} (API products: {', '.join(names)})" for row, _, names in to_file))
    if to_revoke:
        parts.append("no longer needs " + ", ".join(r.policy_key for r in to_revoke))
    return (f"OAN sandbox participant {participant.unique_id} ({participant.company_name or participant.email_id}), "
            f"{'production' if env == PRODUCTION else 'UAT'} apps: " + "; ".join(parts) + ".")


class _PmBackend:
    """OpenG2P PM: one policy request per change (new versions + revocations)."""

    def __init__(self, backend: Backend, participant: Participant, iam: ParticipantIamUser):
        self.target, self.participant, self.iam = backend.pm_target, participant, iam
        self.env = backend.environment
        self.pm_id = pm.pm_partner_id(iam.partner_id)

    def ready(self) -> bool:
        """PM takes policy requests for active partners only."""
        status = self.iam.pm_prod_status if self.env == PRODUCTION else self.iam.pm_status
        return status == str(IamUserStatus.ACTIVE)

    def unsupported(self, policy: dict) -> str | None:
        if policy.get("use_case") and not pm.profile(self.target).use_cases:
            return "This Partner Management release has no use-case policies."
        return None

    def poll(self, row: ParticipantPmPolicy) -> str | None:
        with pm.use_target(self.target):
            try:
                request = pm.get_request(row.request_id)
            except AppError as exc:
                row.error = exc.message[:2000]
                return None
        status = (request or {}).get("status")
        if status == "approved":
            if row.status == str(PmPolicyStatus.REVOKING):
                return "revoked"
            row.status, row.error = str(PmPolicyStatus.ACTIVE), None
            return "approved"
        if status == "rejected" or request is None:
            note = (request or {}).get("review_notes") or ("request not found in PM" if request is None else None)
            if row.status == str(PmPolicyStatus.REVOKING):
                row.status, row.error = str(PmPolicyStatus.ACTIVE), f"Revocation rejected by PM: {note or 'no notes'}"
            else:
                row.status, row.error = str(PmPolicyStatus.REJECTED), note
            return "rejected"
        return None

    def apply(self, to_file, to_revoke, now) -> list[str]:
        description = _description(self.participant, self.env, to_file, to_revoke)
        with pm.use_target(self.target):
            try:
                request = pm.request_policies(
                    self.pm_id, description, [p for _, p, _ in to_file], [_ref(r.policy_key) for r in to_revoke]
                )
                approved = False
                if self.target.auto_approve:
                    pm.approve(request["id"], "Approved in the OAN sandbox.")
                    approved = True
            except AppError as exc:
                logger.warning("PM policy request for %s (%s) failed: %s", self.pm_id, self.env, exc.message)
                for row, _, _ in to_file:
                    row.status, row.error, row.synced_at = str(PmPolicyStatus.FAILED), exc.message[:2000], now
                for row in to_revoke:
                    row.error, row.synced_at = f"Revocation not filed: {exc.message}"[:2000], now
                return [f"request failed: {exc.message}"]
        for row, policy, _ in to_file:
            row.policy, row.request_id, row.error, row.synced_at = policy, request["id"], None, now
            row.status = str(PmPolicyStatus.ACTIVE if approved else PmPolicyStatus.PENDING)
        for row in to_revoke:
            row.request_id, row.error, row.synced_at = request["id"], None, now
            row.status = "_revoked" if approved else str(PmPolicyStatus.REVOKING)
        return [f"request {request['id']}: {len(to_file)} policy(ies), {len(to_revoke)} revocation(s)"
                + (" (auto-approved)" if approved else " (waiting for PM staff)")]


class _CmBackend:
    """COSS Consent Manager: a binding per (audience, registry) with a versioned policy.
    ``request_id`` = ``<binding id>#<version>``."""

    def __init__(self, backend: Backend, participant: Participant, iam: ParticipantIamUser):
        self.target, self.participant, self.iam = backend.cm_target, participant, iam
        self.env = backend.environment
        self.pm_enabled = backend.pm_target is not None
        self.audience = iam.partner_id
        self.pm_id = pm.pm_partner_id(iam.partner_id)

    def ready(self) -> bool:
        """The CM verifies the partner's signatures with PM's copy of its keys: with a PM
        configured the partner must be active there first."""
        if not self.pm_enabled:
            return True
        status = self.iam.pm_prod_status if self.env == PRODUCTION else self.iam.pm_status
        return status == str(IamUserStatus.ACTIVE)

    @staticmethod
    def unsupported(policy: dict) -> str | None:
        if policy.get("use_case"):
            return "The Consent Manager has no use-case policies (registry data scopes only)."
        return None

    @staticmethod
    def fields(policy: dict) -> dict[str, Any]:
        """PM PolicyInput -> CM PolicyUpsert: the same limits; ``allow_partner_consents``
        becomes ``consent_method`` (partner_signed when allowed, else otp: only consents
        the subject confirmed at the CM)."""
        out = {k: policy[k] for k in ("allowed_data_scopes", "allowed_purposes", "allowed_subject_id_types",
                                      "allowed_signing_algs", "max_validity_duration", "fetch_type",
                                      "max_fetch_frequency", "data_life") if policy.get(k)}
        out["consent_method"] = "partner_signed" if policy.get("allow_partner_consents") else "otp"
        return out

    def poll(self, row: ParticipantPmPolicy) -> str | None:
        binding_id, _, version = (row.request_id or "").partition("#")
        with cm.use_target(self.target):
            try:
                versions = cm.list_policies(binding_id)
            except AppError as exc:
                row.error = exc.message[:2000]
                return None
        found = next((v for v in versions if str(v.get("version")) == version), None)
        status = (found or {}).get("status")
        if status in ("active", "superseded"):
            row.status, row.error = str(PmPolicyStatus.ACTIVE), None
            return "approved"
        if status in ("rejected", "stale"):
            row.status, row.error = str(PmPolicyStatus.REJECTED), found.get("status_reason") or status
            return "rejected"
        if status == "failed" or found is None:
            row.status = str(PmPolicyStatus.FAILED)
            row.error = (found or {}).get("status_reason") or "Policy version not found in the Consent Manager."
            return "failed"
        return None

    def apply(self, to_file, to_revoke, now) -> list[str]:
        events = []
        name = self.participant.company_name or self.participant.display_name
        with cm.use_target(self.target):
            for row, policy, _ in to_file:
                controller = policy["data_controller"]
                try:
                    binding = cm.find_binding(self.audience, controller) or cm.create_binding(
                        self.audience, controller, self.pm_id if self.pm_enabled else None, name)
                    if binding.get("status") != "active":
                        binding = cm.set_binding_status(binding["id"], "active")
                    try:
                        saved = cm.upsert_policy(binding["id"], self.fields(policy))
                        version, status = saved.get("version"), saved.get("status")
                    except cm.PolicyPending as exc:
                        version, status = exc.pending_version, "pending"
                    row.policy, row.request_id, row.synced_at = policy, f"{binding['id']}#{version}", now
                    if status == "active":
                        row.status, row.error = str(PmPolicyStatus.ACTIVE), None
                    elif status == "pending":
                        row.status, row.error = str(PmPolicyStatus.PENDING), None
                    else:
                        row.status, row.error = str(PmPolicyStatus.FAILED), saved.get("status_reason") or status
                    events.append(f"{row.policy_key} v{version} {status}")
                except AppError as exc:
                    row.status, row.error, row.synced_at = str(PmPolicyStatus.FAILED), exc.message[:2000], now
                    events.append(f"{row.policy_key} failed: {exc.message}")
            for row in to_revoke:
                controller = _ref(row.policy_key).get("data_controller")
                try:
                    binding = cm.find_binding(self.audience, controller) if controller else None
                    if binding is not None and binding.get("status") != "suspended":
                        cm.set_binding_status(binding["id"], "suspended")
                    row.status = "_revoked"
                    events.append(f"{row.policy_key} binding suspended")
                except AppError as exc:
                    row.error, row.synced_at = f"Revocation not done: {exc.message}"[:2000], now
                    events.append(f"{row.policy_key} suspension failed: {exc.message}")
        return events


def refresh_pending(db: Session) -> int:
    """Re-run the reconcile for participants with policies waiting (open requests, a
    partner not ready yet, failures). Returns how many changed."""
    if not backends():
        return 0
    ids = db.execute(
        select(ParticipantPmPolicy.participant_id)
        .where(ParticipantPmPolicy.status.in_([
            str(PmPolicyStatus.PENDING), str(PmPolicyStatus.REVOKING),
            str(PmPolicyStatus.WAITING), str(PmPolicyStatus.FAILED),
        ]))
        .distinct()
    ).scalars().all()
    return sum(1 for pid in ids if sync_participant(db, pid))


# -------------------------------------------------------------------- views
def rows_out(db: Session, participant_id: int) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ParticipantPmPolicy)
        .where(ParticipantPmPolicy.participant_id == participant_id)
        .order_by(ParticipantPmPolicy.environment, ParticipantPmPolicy.policy_key)
    ).scalars()
    return [
        {
            "environment": r.environment,
            "backend": r.backend,
            "policy_key": r.policy_key,
            "status": r.status,
            "products": list(r.products or []),
            "policy": r.policy,
            "request_id": r.request_id,
            "error": r.error,
            "synced_at": r.synced_at,
        }
        for r in rows
    ]


def catalogue(environment: str = UAT) -> dict[str, Any]:
    """Policy choices for the product form, from the environment's backend: PM's
    catalogue, or the CM's known controllers and scopes."""
    backend = backend_for(environment)
    if backend is None:
        return {"enabled": False, "backend": None, "sources": []}
    try:
        if backend.kind == "pm":
            if not pm.profile(backend.pm_target).catalogue:
                return {"enabled": True, "backend": "pm", "sources": []}
            with pm.use_target(backend.pm_target):
                return {"enabled": True, "backend": "pm", "sources": pm.catalogue()}
        with cm.use_target(backend.cm_target):
            meta = cm.meta()
        scopes = [{"id": s} for s in meta.get("known_data_scopes") or []]
        return {"enabled": True, "backend": "cm", "sources": [
            {"kind": "scopes", "data_controller": c, "label": c, "items": scopes}
            for c in meta.get("known_controller_ids") or []
        ]}
    except AppError as exc:
        return {"enabled": True, "backend": backend.kind, "sources": [], "error": exc.message}
