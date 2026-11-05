"""Participant apps: create, request API products, issue and revoke keys.

Lifecycle (Apigee "developer app"):

1. A participant with UAT access creates an app and picks API products.
   The app waits for an administrator (``AppStatus.PENDING``): it has no
   key, and nothing is written to the gateway.
2. The administrator approves the whole app (every open product request is
   granted with it) or one of its product requests, or rejects it with a
   reason. The first approval activates the app and issues its first
   credential - API key + secret. The owner reads both under My Apps (the
   portal masks them until revealed); administrators see only the prefix.
3. Each later product request is approved at once (``ApprovalType.AUTO``) or
   waits for an administrator (``MANUAL``). Access an administrator revoked
   is never re-granted automatically.
4. Every change is written to the gateway (``app_gateway_service``); the key
   works there only for the routes of approved products.
5. Keys are rotated by issuing a second credential and revoking the first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core import crypto
from app.core.context import admin_country_scope, assert_in_admin_scope
from app.core.deps import AdminPrincipal, ParticipantPrincipal
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.pagination import Page
from app.integrations import keycloak
from app.models.app import (
    ApiProduct,
    ParticipantApp,
    ParticipantAppCredential,
    ParticipantAppProduct,
)
from app.models.enums import (
    ApprovalType,
    AppStatus,
    CredentialStatus,
    Environment,
    GatewaySyncStatus,
    SubscriptionStatus,
)
from app.models.participant import Participant
from app.repositories.app_repository import (
    ApiProductRepository,
    AppCredentialRepository,
    AppSubscriptionRepository,
    ParticipantAppRepository,
)
from app.repositories.participant_repository import ParticipantRepository
from app.schemas.app import (
    AdminAppListQuery,
    AdminAppOut,
    AppCreate,
    AppCreatedOut,
    AppCredentialOut,
    AppOut,
    AppSubscriptionOut,
    AppUpdate,
    IssuedCredentialOut,
)
from app.services import app_gateway_service, audit_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_templated

APP_STATUS_LABELS = {
    int(AppStatus.PENDING): "Awaiting approval",
    int(AppStatus.ACTIVE): "Active",
    int(AppStatus.REVOKED): "Revoked",
    int(AppStatus.REJECTED): "Rejected",
}
SUBSCRIPTION_LABELS = {
    int(SubscriptionStatus.PENDING): "Pending approval",
    int(SubscriptionStatus.APPROVED): "Approved",
    int(SubscriptionStatus.REJECTED): "Rejected",
    int(SubscriptionStatus.REVOKED): "Revoked",
}
CREDENTIAL_LABELS = {int(CredentialStatus.ACTIVE): "Active", int(CredentialStatus.REVOKED): "Revoked"}


# ============================================================ participant
def available_products(db: Session, participant: Participant) -> list[dict[str, Any]]:
    """Published API products a participant can ask for, with their endpoints."""
    from app.services.api_product_service import endpoint_rows

    repo = ApiProductRepository(db)
    return [
        {
            "api_product_id": p.api_product_id,
            "name": p.name,
            "display_name": p.display_name,
            "description": p.description,
            "approval_type": p.approval_type,
            "rate_limit_per_minute": p.rate_limit_per_minute,
            "quota_per_day": p.quota_per_day,
            "endpoints": [row.model_dump() for row in endpoint_rows(db, repo.endpoints(p.api_product_id))],
        }
        for p in repo.published(participant.country_code)
    ]


def list_apps(db: Session, participant: Participant) -> list[AppOut]:
    return [app_out(db, app, reveal_key=True) for app in ParticipantAppRepository(db).for_participant(participant.participant_id)]


def get_app(db: Session, participant: Participant, app_uid: str) -> AppOut:
    return app_out(db, _owned(db, participant, app_uid), reveal_key=True)


def create_app(db: Session, principal: ParticipantPrincipal, payload: AppCreate) -> AppCreatedOut:
    participant = principal.participant
    if not participant.is_uat_approved:
        raise ForbiddenError("Your account needs UAT access before you can create apps.")
    repo = ParticipantAppRepository(db)
    environment = str(Environment.UAT)
    if repo.count(participant_id=participant.participant_id) >= settings.MAX_APPS_PER_PARTICIPANT:
        raise ValidationError(f"You can have at most {settings.MAX_APPS_PER_PARTICIPANT} apps.")
    if repo.name_taken(participant.participant_id, payload.name, environment):
        raise ConflictError(f"You already have an app named '{payload.name}'.")
    products = _published_products(db, participant, payload.api_product_ids)

    app = ParticipantApp(
        participant_id=participant.participant_id,
        name=payload.name,
        description=payload.description,
        callback_url=payload.callback_url,
        allowed_ips=payload.allowed_ips,
        environment=environment,
        # No key and nothing at the gateway until an administrator approves.
        status=int(AppStatus.PENDING),
        gateway_status=str(GatewaySyncStatus.PENDING),
        added_by=participant.participant_id,
        modify_by=participant.participant_id,
    )
    db.add(app)
    db.flush()
    app.gateway_consumer = app_gateway_service.consumer_name(app)
    for product in products:
        _request_product(app, product, participant.participant_id)
    db.commit()

    audit_service.record_participant(
        db, principal, Action.APP_CREATE, entity="participant_app", entity_id=app.app_id,
        description=f"Created app '{app.name}' requesting {len(products)} API product(s); awaiting approval",
    )
    app_gateway_service.sync_app(db, app)
    return AppCreatedOut(app=app_out(db, app, reveal_key=True), credential=None)


def update_app(db: Session, principal: ParticipantPrincipal, app_uid: str, payload: AppUpdate) -> AppOut:
    app = _owned(db, principal.participant, app_uid)
    if payload.name and payload.name != app.name:
        if ParticipantAppRepository(db).name_taken(app.participant_id, payload.name, app.environment, app.app_id):
            raise ConflictError(f"You already have an app named '{payload.name}'.")
        app.name = payload.name
    fields = payload.model_dump(exclude_unset=True)
    if "description" in fields:
        app.description = payload.description
    if "callback_url" in fields:
        app.callback_url = payload.callback_url
    ips_changed = payload.allowed_ips is not None and payload.allowed_ips != list(app.allowed_ips or [])
    if ips_changed:
        app.allowed_ips = payload.allowed_ips
    app.modify_by = principal.id
    db.commit()
    audit_service.record_participant(
        db, principal, Action.APP_UPDATE, entity="participant_app", entity_id=app.app_id,
        description=f"Updated app '{app.name}'"
        + (f"; IP whitelist: {', '.join(app.allowed_ips) or 'any address'}" if ips_changed else ""),
    )
    if ips_changed:
        app_gateway_service.sync_app(db, app)
    return app_out(db, app, reveal_key=True)


def delete_app(db: Session, principal: ParticipantPrincipal, app_uid: str) -> None:
    app = _owned(db, principal.participant, app_uid)
    now = datetime.now(UTC)
    for credential in app.credentials:
        if credential.status == int(CredentialStatus.ACTIVE):
            credential.status, credential.revoked_date = int(CredentialStatus.REVOKED), now
    app.is_deleted, app.is_enabled, app.modify_by = True, False, principal.id
    db.commit()
    audit_service.record_participant(
        db, principal, Action.APP_DELETE, entity="participant_app", entity_id=app.app_id,
        description=f"Deleted app '{app.name}'",
    )
    app_gateway_service.sync_app(db, app)


def add_products(
    db: Session, principal: ParticipantPrincipal, app_uid: str, api_product_ids: list[int]
) -> AppOut:
    app = _owned(db, principal.participant, app_uid, active_only=True, allow_pending=True)
    products = _published_products(db, principal.participant, api_product_ids)
    for product in products:
        _request_product(app, product, principal.id)
    db.commit()
    audit_service.record_participant(
        db, principal, Action.APP_PRODUCT_REQUEST, entity="participant_app", entity_id=app.app_id,
        description=f"App '{app.name}' requested {', '.join(p.name for p in products)}",
    )
    app_gateway_service.sync_app(db, app)
    return app_out(db, app, reveal_key=True)


def remove_product(db: Session, principal: ParticipantPrincipal, app_uid: str, api_product_id: int) -> AppOut:
    app = _owned(db, principal.participant, app_uid)
    subscription = AppSubscriptionRepository(db).find(app.app_id, api_product_id)
    if subscription is None:
        raise NotFoundError("This app has not requested that API product.")
    if subscription.status == int(SubscriptionStatus.REVOKED):
        # Kept, so the administrator's decision is not lost by re-requesting.
        raise ValidationError("An administrator revoked this access; it cannot be withdrawn.")
    name = subscription.api_product.name
    app.subscriptions.remove(subscription)
    db.commit()
    audit_service.record_participant(
        db, principal, Action.APP_PRODUCT_WITHDRAW, entity="participant_app", entity_id=app.app_id,
        description=f"App '{app.name}' withdrew {name}",
    )
    app_gateway_service.sync_app(db, app)
    return app_out(db, app, reveal_key=True)


def issue_credential(db: Session, principal: ParticipantPrincipal, app_uid: str) -> IssuedCredentialOut:
    app = _owned(db, principal.participant, app_uid, active_only=True)
    if AppCredentialRepository(db).active_count(app.app_id) >= settings.MAX_ACTIVE_CREDENTIALS_PER_APP:
        raise ValidationError(
            f"An app can have {settings.MAX_ACTIVE_CREDENTIALS_PER_APP} active keys. Revoke one first."
        )
    credential = _new_credential(app, principal.id)
    db.commit()
    audit_service.record_participant(
        db, principal, Action.APP_CREDENTIAL_ISSUE, entity="participant_app", entity_id=app.app_id,
        description=f"Issued key {credential.api_key_prefix}… for app '{app.name}'",
    )
    app_gateway_service.sync_app(db, app)
    return _issued(credential)


def revoke_credential(db: Session, principal: ParticipantPrincipal, app_uid: str, credential_uid: str) -> AppOut:
    app = _owned(db, principal.participant, app_uid)
    credential = next((c for c in app.credentials if str(c.unique_id) == credential_uid), None)
    if credential is None:
        raise NotFoundError("Key not found.")
    if credential.status == int(CredentialStatus.REVOKED):
        raise ValidationError("This key is already revoked.")
    credential.status, credential.revoked_date = int(CredentialStatus.REVOKED), datetime.now(UTC)
    credential.modify_by = principal.id
    db.commit()
    audit_service.record_participant(
        db, principal, Action.APP_CREDENTIAL_REVOKE, entity="participant_app", entity_id=app.app_id,
        description=f"Revoked key {credential.api_key_prefix}… of app '{app.name}'",
    )
    app_gateway_service.sync_app(db, app)
    return app_out(db, app, reveal_key=True)


def try_it_key(db: Session, participant: Participant, app_uid: str) -> str:
    """The API key a try-it call made "as this app" sends to the gateway."""
    credential = _newest_key(db, participant, app_uid)
    credential.last_used_date = datetime.now(UTC)
    db.commit()
    return crypto.decrypt(credential.api_key_encrypted)


#: Token claims the portal shows after "Get token" (the gateway checks these).
TOKEN_CLAIMS_SHOWN = (
    "iss", "azp", "iat", "exp", "oan_app", "participant_uid", "oan_environments", "oan_routes",
)


def gateway_auth() -> dict[str, Any]:
    """How the gateway identifies a caller, for the portal's try-it page."""
    oauth = settings.GATEWAY_PARTNER_AUTH == "oauth"
    return {
        "mode": settings.GATEWAY_PARTNER_AUTH,
        "app_key_header": settings.GATEWAY_APP_KEY_HEADER,
        "token_header": settings.GATEWAY_PARTNER_TOKEN_HEADER,
        "token_url": keycloak.token_url(public=True) if oauth else None,
        "grant_type": "client_credentials" if oauth else None,
    }


def get_app_token(db: Session, participant: Participant, app_uid: str) -> dict[str, Any]:
    """The app's access token (GATEWAY_PARTNER_AUTH=oauth), as a partner gets it.

    The OAuth client-credentials request with the app's newest API key + secret,
    made by the sandbox so the secret stays on the server: the portal shows the
    request (URL, client id, grant), the token, its expiry and claims, and puts
    the token in the try-it headers.
    """
    if settings.GATEWAY_PARTNER_AUTH != "oauth":
        raise ValidationError("App tokens are used only when the gateway checks OAuth app tokens.")
    credential = _newest_key(db, participant, app_uid)
    client_id = crypto.decrypt(credential.api_key_encrypted)
    body = keycloak.request_app_token(client_id, crypto.decrypt(credential.api_secret_encrypted))
    credential.last_used_date = datetime.now(UTC)
    db.commit()
    token = body["access_token"]
    claims = keycloak.unverified_claims(token)
    expires_in = int(body.get("expires_in") or 0)
    return {
        "token_url": keycloak.token_url(public=True),
        "grant_type": "client_credentials",
        "client_id": client_id,
        "header": settings.GATEWAY_PARTNER_TOKEN_HEADER,
        "access_token": token,
        "token_type": body.get("token_type", "Bearer"),
        "expires_in": expires_in,
        "expires_at": (
            datetime.fromtimestamp(claims["exp"], UTC).isoformat()
            if isinstance(claims.get("exp"), int) else None
        ),
        "claims": {name: claims[name] for name in TOKEN_CLAIMS_SHOWN if name in claims},
    }


def owned_app_id(db: Session, participant: Participant, app_uid: str) -> int:
    """Numeric id of one of the participant's apps (API history keeps it)."""
    return _owned(db, participant, app_uid).app_id


def app_key(db: Session, participant: Participant, app_uid: str) -> str:
    """The app's newest active API key, for a code sample (not a use of the key)."""
    return crypto.decrypt(_newest_key(db, participant, app_uid).api_key_encrypted)


def _newest_key(db: Session, participant: Participant, app_uid: str) -> ParticipantAppCredential:
    app = _owned(db, participant, app_uid, active_only=True)
    active = AppCredentialRepository(db).for_app(app.app_id, active_only=True)
    if not active:
        raise ValidationError(f"App '{app.name}' has no active key. Issue one under My Apps.")
    return active[0]


# ================================================================== admin
def admin_list(db: Session, query: AdminAppListQuery, admin: AdminPrincipal) -> Page:
    repo = ParticipantAppRepository(db)
    filters = query.filters or {}
    stmt = repo.admin_stmt(
        status=query.status if query.status is not None else filters.get("status"),
        participant_id=query.participant_id or filters.get("participant_id"),
        api_product_id=query.api_product_id or filters.get("api_product_id"),
        pending_only=query.pending_only or bool(filters.get("pending_only")),
        country_code=admin_country_scope(),
    )
    page = repo.paginate(query.page, query.limit, query.search, query.sort_by, query.sort_dir, stmt=stmt)
    page.rows = _admin_rows(db, page.rows)
    return page


def admin_get(db: Session, app_id: int) -> AdminAppOut:
    return _admin_rows(db, [_require(db, app_id)])[0]


def decide_product(
    db: Session,
    admin: AdminPrincipal,
    app_id: int,
    api_product_id: int,
    status: SubscriptionStatus,
    remarks: str | None,
) -> AdminAppOut:
    app = _require(db, app_id)
    subscription = AppSubscriptionRepository(db).find(app.app_id, api_product_id)
    if subscription is None:
        raise NotFoundError("This app has not requested that API product.")
    allowed = {
        SubscriptionStatus.APPROVED: {SubscriptionStatus.PENDING, SubscriptionStatus.REJECTED, SubscriptionStatus.REVOKED},
        SubscriptionStatus.REJECTED: {SubscriptionStatus.PENDING},
        SubscriptionStatus.REVOKED: {SubscriptionStatus.APPROVED},
    }[status]
    if SubscriptionStatus(subscription.status) not in allowed:
        raise ValidationError(
            f"A {SUBSCRIPTION_LABELS[subscription.status].lower()} request cannot be "
            f"{SUBSCRIPTION_LABELS[int(status)].lower()}."
        )
    subscription.status = int(status)
    subscription.remarks = remarks
    subscription.decided_by = admin.id
    subscription.decided_date = datetime.now(UTC)
    subscription.modify_by = admin.id
    db.commit()
    if status == SubscriptionStatus.APPROVED and app.status in (
        int(AppStatus.PENDING), int(AppStatus.REJECTED)
    ):
        # Granting a product to a waiting app is its approval: it gets its key.
        _activate(db, app, admin, remarks)
    audit_service.record_admin(
        db, admin, Action.APP_PRODUCT_DECISION, entity="participant_app", entity_id=app.app_id,
        description=f"{SUBSCRIPTION_LABELS[int(status)]}: {subscription.api_product.name} for app '{app.name}'",
        changes={"remarks": remarks} if remarks else None,
    )
    app_gateway_service.sync_app(db, app)
    return admin_get(db, app_id)


def approve_app(db: Session, admin: AdminPrincipal, app_id: int, remarks: str | None) -> AdminAppOut:
    """Approve a new (or rejected) app: every open product request is granted,
    the app becomes active and its first API key + secret are issued."""
    app = _require(db, app_id)
    if app.status not in (int(AppStatus.PENDING), int(AppStatus.REJECTED)):
        raise ValidationError(
            f"This app is {APP_STATUS_LABELS[app.status].lower()}; only a new or rejected app can be approved."
        )
    now = datetime.now(UTC)
    granted = []
    # Requests still open, and (for a rejected app) those declined with it.
    reopen = {int(SubscriptionStatus.PENDING)}
    if app.status == int(AppStatus.REJECTED):
        reopen.add(int(SubscriptionStatus.REJECTED))
    for subscription in app.subscriptions:
        if subscription.status in reopen:
            subscription.status = int(SubscriptionStatus.APPROVED)
            subscription.remarks = remarks or "Approved with the app."
            subscription.decided_by, subscription.decided_date, subscription.modify_by = admin.id, now, admin.id
            granted.append(subscription.api_product.name)
    _activate(db, app, admin, remarks)
    audit_service.record_admin(
        db, admin, Action.APP_APPROVE, entity="participant_app", entity_id=app.app_id,
        description=f"Approved app '{app.name}'" + (f" with {', '.join(granted)}" if granted else ""),
        changes={"remarks": remarks} if remarks else None,
    )
    app_gateway_service.sync_app(db, app)
    return admin_get(db, app_id)


def reject_app(db: Session, admin: AdminPrincipal, app_id: int, reason: str) -> AdminAppOut:
    """Decline a new app: no key is ever issued; the participant sees the reason."""
    app = _require(db, app_id)
    if app.status != int(AppStatus.PENDING):
        raise ValidationError(
            f"This app is {APP_STATUS_LABELS[app.status].lower()}; only an app awaiting approval can be rejected."
        )
    now = datetime.now(UTC)
    for subscription in app.subscriptions:
        if subscription.status == int(SubscriptionStatus.PENDING):
            subscription.status = int(SubscriptionStatus.REJECTED)
            subscription.remarks = reason
            subscription.decided_by, subscription.decided_date, subscription.modify_by = admin.id, now, admin.id
    app.status, app.revoked_reason, app.modify_by = int(AppStatus.REJECTED), reason, admin.id
    db.commit()
    owner = db.get(Participant, app.participant_id)
    if owner is not None:
        send_templated(
            db, TemplateCode.APP_REJECTED, owner.email_id,
            {"name": owner.display_name, "app_name": app.name, "reason": reason},
        )
    audit_service.record_admin(
        db, admin, Action.APP_REJECT, entity="participant_app", entity_id=app.app_id,
        description=f"Rejected app '{app.name}': {reason}",
    )
    app_gateway_service.sync_app(db, app)
    return admin_get(db, app_id)


def _activate(db: Session, app: ParticipantApp, admin: AdminPrincipal, remarks: str | None) -> None:
    """The approval itself: the app becomes active and, if it has none, gets its first key."""
    app.status, app.revoked_reason, app.modify_by = int(AppStatus.ACTIVE), None, admin.id
    if not any(c.status == int(CredentialStatus.ACTIVE) for c in app.credentials):
        _new_credential(app, admin.id)
    db.commit()
    owner = db.get(Participant, app.participant_id)
    if owner is not None:
        send_templated(
            db, TemplateCode.APP_APPROVED, owner.email_id,
            {"name": owner.display_name, "app_name": app.name, "remarks": remarks or ""},
        )


def revoke_app(db: Session, admin: AdminPrincipal, app_id: int, reason: str) -> AdminAppOut:
    app = _require(db, app_id)
    if app.status == int(AppStatus.REVOKED):
        raise ValidationError("This app is already revoked.")
    if app.status != int(AppStatus.ACTIVE):
        raise ValidationError("Only an active app can be revoked; reject a new app instead.")
    app.status, app.revoked_reason, app.modify_by = int(AppStatus.REVOKED), reason, admin.id
    db.commit()
    audit_service.record_admin(
        db, admin, Action.APP_REVOKE, entity="participant_app", entity_id=app.app_id,
        description=f"Revoked app '{app.name}': {reason}",
    )
    app_gateway_service.sync_app(db, app)
    return admin_get(db, app_id)


def restore_app(db: Session, admin: AdminPrincipal, app_id: int) -> AdminAppOut:
    app = _require(db, app_id)
    if app.status == int(AppStatus.ACTIVE):
        raise ValidationError("This app is already active.")
    if app.status != int(AppStatus.REVOKED):
        raise ValidationError("Only a revoked app can be restored; approve a new or rejected app instead.")
    app.status, app.revoked_reason, app.modify_by = int(AppStatus.ACTIVE), None, admin.id
    db.commit()
    audit_service.record_admin(
        db, admin, Action.APP_RESTORE, entity="participant_app", entity_id=app.app_id,
        description=f"Restored app '{app.name}'",
    )
    app_gateway_service.sync_app(db, app)
    return admin_get(db, app_id)


def resync(db: Session, admin: AdminPrincipal, app_id: int) -> AdminAppOut:
    app = _require(db, app_id)
    app_gateway_service.sync_app(db, app)
    audit_service.record_admin(
        db, admin, Action.APP_GATEWAY_SYNC, entity="participant_app", entity_id=app.app_id,
        description=f"Re-synced app '{app.name}' to the gateway: {app.gateway_status}",
    )
    return admin_get(db, app_id)


# ========================================================= serialisation
def app_out(db: Session, app: ParticipantApp, reveal_key: bool) -> AppOut:
    return AppOut(**_app_fields(db, app, reveal_key))


def _app_fields(db: Session, app: ParticipantApp, reveal_key: bool) -> dict[str, Any]:
    from app.services.api_product_service import endpoint_rows

    per_minute, per_day = (
        app_gateway_service.effective_limits(app) if settings.GATEWAY_RATE_LIMIT_ENABLED else (None, None)
    )
    # The APIs behind each product, so the owner sees what the app may call.
    products = ApiProductRepository(db)
    endpoints = {
        s.api_product_id: endpoint_rows(db, products.endpoints(s.api_product_id)) for s in app.subscriptions
    }
    return {
        "app_id": str(app.unique_id),
        "name": app.name,
        "description": app.description,
        "callback_url": app.callback_url,
        "environment": app.environment,
        "status": app.status,
        "status_label": APP_STATUS_LABELS.get(app.status, str(app.status)),
        "revoked_reason": app.revoked_reason,
        "allowed_ips": list(app.allowed_ips or []),
        "rate_limit_per_minute": per_minute,
        "quota_per_day": per_day,
        "gateway_consumer": app.gateway_consumer,
        "gateway_status": app.gateway_status,
        # The raw error quotes the gateway's Admin API; only administrators see it.
        "gateway_error": (
            app.gateway_error
            if not reveal_key
            else ("The gateway could not be updated; an administrator has been notified."
                  if app.gateway_error else None)
        ),
        "gateway_synced_at": app.gateway_synced_at,
        "gateway_warnings": list(app.gateway_warnings or []),
        "products": [
            AppSubscriptionOut(
                api_product_id=s.api_product_id,
                name=s.api_product.name,
                display_name=s.api_product.display_name,
                rate_limit_per_minute=s.api_product.rate_limit_per_minute,
                quota_per_day=s.api_product.quota_per_day,
                status=s.status,
                status_label=SUBSCRIPTION_LABELS.get(s.status, str(s.status)),
                remarks=s.remarks,
                requested_date=s.added_date,
                decided_date=s.decided_date,
                endpoints=endpoints[s.api_product_id],
            )
            for s in sorted(app.subscriptions, key=lambda s: s.id or 0)
        ],
        "credentials": [
            _credential_out(c, reveal_key)
            for c in sorted(app.credentials, key=lambda c: (c.status, -(c.credential_id or 0)))
        ],
        "added_date": app.added_date,
        "modify_date": app.modify_date,
    }


def _credential_out(credential: ParticipantAppCredential, reveal_key: bool) -> AppCredentialOut:
    """``reveal_key``: the owner's view, with key and secret of an active credential."""
    active = credential.status == int(CredentialStatus.ACTIVE)
    secret = crypto.decrypt(credential.api_secret_encrypted)
    return AppCredentialOut(
        credential_id=str(credential.unique_id),
        api_key=crypto.decrypt(credential.api_key_encrypted) if reveal_key and active else None,
        api_secret=secret if reveal_key and active else None,
        api_key_prefix=credential.api_key_prefix,
        api_secret_hint="••••" + secret[-4:],
        status=credential.status,
        status_label=CREDENTIAL_LABELS.get(credential.status, str(credential.status)),
        issued_date=credential.issued_date,
        revoked_date=credential.revoked_date,
        last_used_date=credential.last_used_date,
    )


def _issued(credential: ParticipantAppCredential) -> IssuedCredentialOut:
    return IssuedCredentialOut(**_credential_out(credential, True).model_dump())


def _admin_rows(db: Session, apps: list[ParticipantApp]) -> list[AdminAppOut]:
    owners = {
        p.participant_id: p
        for p in ParticipantRepository(db).get_many({a.participant_id for a in apps})
    }
    rows = []
    for app in apps:
        owner = owners.get(app.participant_id)
        rows.append(
            AdminAppOut(
                **_app_fields(db, app, reveal_key=False),
                id=app.app_id,
                participant_id=app.participant_id,
                participant_name=owner.full_name if owner else None,
                participant_email=owner.email_id if owner else None,
                company_name=owner.company_name if owner else None,
                gateway_routes=list(app.gateway_routes or []),
            )
        )
    return rows


# ================================================================ helpers
def _owned(
    db: Session,
    participant: Participant,
    app_uid: str,
    active_only: bool = False,
    allow_pending: bool = False,
) -> ParticipantApp:
    """One of the participant's apps.

    ``active_only`` refuses a revoked or rejected app, and a waiting one
    unless ``allow_pending`` (requesting products is fine before approval;
    keys and calls are not).
    """
    app = ParticipantAppRepository(db).get_owned(participant.participant_id, app_uid)
    if app is None:
        raise NotFoundError("App not found.")
    if active_only and app.status != int(AppStatus.ACTIVE):
        if app.status == int(AppStatus.PENDING):
            if not allow_pending:
                raise ForbiddenError(
                    "This app is awaiting approval; its API key and secret are issued "
                    "when an administrator approves it."
                )
        elif app.status == int(AppStatus.REJECTED):
            raise ForbiddenError("An administrator rejected this app.")
        else:
            raise ForbiddenError("This app was revoked by an administrator.")
    if active_only and not participant.is_uat_approved:
        raise ForbiddenError("Your account no longer has UAT access.")
    return app


def _require(db: Session, app_id: int) -> ParticipantApp:
    app = ParticipantAppRepository(db).get(app_id)
    owner = db.get(Participant, app.participant_id) if app is not None else None
    if app is None or not assert_in_admin_scope(owner.country_code if owner else None):
        raise NotFoundError("App not found.")
    return app


def _published_products(db: Session, participant: Participant, ids: list[int]) -> list[ApiProduct]:
    wanted = list(dict.fromkeys(ids))
    available = {p.api_product_id: p for p in ApiProductRepository(db).published(participant.country_code)}
    unknown = [i for i in wanted if i not in available]
    if unknown:
        raise ValidationError(f"API product(s) not available: {', '.join(map(str, unknown))}.")
    return [available[i] for i in wanted]


def _request_product(app: ParticipantApp, product: ApiProduct, actor_id: int) -> None:
    existing = next((s for s in app.subscriptions if s.api_product_id == product.api_product_id), None)
    if existing is not None and existing.status in (int(SubscriptionStatus.PENDING), int(SubscriptionStatus.APPROVED)):
        return
    auto = product.approval_type == str(ApprovalType.AUTO) and (
        existing is None or existing.status != int(SubscriptionStatus.REVOKED)
    )
    status = SubscriptionStatus.APPROVED if auto else SubscriptionStatus.PENDING
    if existing is None:
        existing = ParticipantAppProduct(api_product=product, added_by=actor_id)
        app.subscriptions.append(existing)
    existing.status = int(status)
    existing.remarks = "Approved automatically." if auto else None
    existing.decided_by = None
    existing.decided_date = datetime.now(UTC) if auto else None
    existing.modify_by = actor_id


def _new_credential(app: ParticipantApp, actor_id: int) -> ParticipantAppCredential:
    """A fresh API key + secret on the app (stored encrypted; read back with ``crypto``)."""
    api_key, secret = crypto.new_api_key(), crypto.new_api_secret()
    credential = ParticipantAppCredential(
        api_key_encrypted=crypto.encrypt(api_key),
        api_secret_encrypted=crypto.encrypt(secret),
        api_key_hash=crypto.sha256_hex(api_key),
        api_key_prefix=api_key[: crypto.KEY_PREFIX_LENGTH],
        status=int(CredentialStatus.ACTIVE),
        added_by=actor_id,
        modify_by=actor_id,
    )
    app.credentials.append(credential)
    return credential
