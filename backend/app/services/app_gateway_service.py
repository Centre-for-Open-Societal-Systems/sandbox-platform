"""Write an app to the API gateway as it is saved in the sandbox.

One app is one APISIX consumer (``ParticipantApp.gateway_consumer``):

* each active credential becomes two consumer credentials - ``key-auth``
  (``<credential uid>-key``, the API key) and ``hmac-auth``
  (``<credential uid>-hmac``, key + secret for signed requests); revoked ones
  are deleted;
* ``consumer-restriction`` (``type: route_id``) whitelists the routes the
  app's approved API products cover. Routes are left untouched, so the ADC
  sync that owns them cannot undo a grant;
* optional, per app: ``ip-restriction`` (the app's IP whitelist),
  ``limit-count`` (the most generous per-minute / per-day limits of its
  approved products, GATEWAY_RATE_LIMIT_ENABLED) and ``http-logger`` (call
  records posted to the sandbox's logs callback, GATEWAY_LOG_INGEST_ENABLED).

A route is granted only when every operation it serves is in the app's
products: a route serving 12 paths cannot grant 7 of them. Such routes, and
granted endpoints the gateway does not serve, are recorded in
``gateway_warnings``. Routes without an authentication plugin are open to
everybody and need no grant.

With GATEWAY_PARTNER_AUTH=oauth nothing is written to the gateway: the routes
check the app's Keycloak token; each active key is a Keycloak client instead.
With GATEWAY_SCOPES the token carries the scopes of the app's products in the
standard ``scope`` claim (``gateway_scope_service``), plus GATEWAY_TOKEN_AUDIENCE
in ``aud``, and the routes check those: the sandbox needs nothing from the
gateway. While GATEWAY_LEGACY_ROUTE_CLAIM is on (or without GATEWAY_SCOPES) the
token also carries the granted route ids in ``oan_routes``, which the sandbox
reads from the routes (a viewer admin key is enough). What the
consumer plugins above did, the routes do from the token: the app's IP
whitelist (``oan_ips``) and the limits of its products (``oan_limit_minute``,
``oan_limit_day``, with GATEWAY_RATE_LIMIT_ENABLED), and they carry
``http-logger`` themselves (``gateway_log_service``). A change reaches the
gateway with the next token: one already issued keeps its values until it
expires (five minutes).

Every app belongs to one environment (``ParticipantApp.environment``) and has
its own keys there: a UAT app works only on UAT, a production app (made with
"Move to production") only on production. Its clients / consumer go to that
environment's Keycloak and gateway - production's own when KEYCLOAK_PROD_URL /
GATEWAY_PROD_ADMIN_URL are set, else the main ones - and its tokens name only
that environment (``oan_environments``). A production app's keys work only while
its owner is approved for production.

Route ids are resolved from the routes the last "Pull from gateway" kept
(``GatewayRouteSnapshot``, ``routes_for``); only a gateway never pulled is read
live. So with GATEWAY_PARTNER_AUTH=oauth, once pulled, approving an app or
changing a product needs Keycloak but not the gateway. A pull re-syncs the apps
whose route ids changed (``resync_after_pull``).

``sync_app`` is idempotent and never raises: a gateway failure is stored on
the app (``gateway_status`` FAILED, ``gateway_error``) and can be retried.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core import crypto
from app.core.exceptions import AppError, ValidationError
from app.core.logging import get_logger
from app.integrations import gateway, keycloak
from app.models.app import (
    GatewayRouteSnapshot,
    ParticipantApp,
    ParticipantAppCredential,
)
from app.models.catalog import Endpoint, Product
from app.models.enums import (
    AppStatus,
    CredentialStatus,
    Environment,
    GatewaySyncStatus,
    SubscriptionStatus,
)
from app.models.participant import Participant
from app.repositories.app_repository import ApiProductRepository
from app.services import gateway_scope_service, pm_policy_service

logger = get_logger(__name__)

#: Whitelist entry for an app with no granted route (the plugin needs one).
NO_ROUTE = "oan-sandbox-no-route"
REJECTED_MESSAGE = "This app has no access to this API. Request the API product that includes it."
IP_REJECTED_MESSAGE = "This app does not accept calls from your IP address. Add it to the app's IP whitelist."
RATE_LIMIT_MESSAGE = "Rate limit exceeded for this app. Try again later or ask for a higher limit."
#: What APISIX's http-logger sends per call. No credential header is in it,
#: so API keys and bearer tokens never leave the gateway.
LOG_FORMAT = {
    "request_id": "$request_id",
    "time": "$time_iso8601",
    "consumer": "$consumer_name",
    "route_id": "$route_id",
    "method": "$request_method",
    "host": "$host",
    "uri": "$uri",
    "query": "$args",
    "status": "$status",
    "request_time": "$request_time",
    "upstream_time": "$upstream_response_time",
    "client_ip": "$remote_addr",
    "request_length": "$request_length",
    "bytes_sent": "$bytes_sent",
    "user_agent": "$http_user_agent",
    "sandbox_txn": "$http_x_oan_sandbox_transaction",
}


def consumer_name(app: ParticipantApp) -> str:
    return "oanapp_" + str(app.unique_id).replace("-", "")


def credential_is_live(credential: ParticipantAppCredential) -> bool:
    """Active and not past its expiry: only these reach the gateway."""
    if credential.status != int(CredentialStatus.ACTIVE):
        return False
    expires = credential.expires_date
    if expires is None:
        return True
    if expires.tzinfo is None:  # SQLite hands datetimes back naive
        expires = expires.replace(tzinfo=UTC)
    return expires > datetime.now(UTC)


def credential_ids(credential: ParticipantAppCredential) -> tuple[str, str]:
    return f"{credential.unique_id}-key", f"{credential.unique_id}-hmac"


def sync_app(
    db: Session,
    app: ParticipantApp,
    routes: list[gateway.GatewayRoute] | None = None,
    policies: bool = True,
) -> ParticipantApp:
    """Bring the gateway in line with ``app``; ``routes`` (of the app's environment's
    gateway) save a fetch when syncing many. ``policies``: then reconcile the owner's
    Partner Management policies (``pm_policy_service``; ``sync_apps`` does it once per
    owner)."""
    try:
        return _sync_app(db, app, routes)
    finally:
        if policies:
            pm_policy_service.sync_participant(db, app.participant_id)


def _sync_app(
    db: Session, app: ParticipantApp, routes: list[gateway.GatewayRoute] | None = None
) -> ParticipantApp:
    if not gateway.app_sync_configured():
        app.gateway_status = str(GatewaySyncStatus.DISABLED)
        app.gateway_error = None
        db.commit()
        return app
    try:
        owner = db.get(Participant, app.participant_id)
        with keycloak.use_realm(keycloak.realm_for(app.environment)), gateway.use_target(
            gateway.target_for(app.environment)
        ):
            if app.is_deleted or app.status != int(AppStatus.ACTIVE) or not owner_active(owner, app.environment):
                if oauth_clients():
                    _sync_oauth_clients(app, None)
                elif app.gateway_consumer:
                    gateway.delete_consumer(app.gateway_consumer)
                app.gateway_routes, app.gateway_warnings, app.gateway_scopes = [], [], []
            elif oauth_clients():
                # The routes check the token, not a consumer: never write to the gateway.
                # Scopes come from configuration; route ids (legacy) from the routes.
                warnings: list[str] = []
                if gateway_scope_service.enabled():
                    app.gateway_scopes, warnings = gateway_scope_service.app_scopes(db, app)
                else:
                    app.gateway_scopes = []
                if needs_routes():
                    app.gateway_routes, route_warnings = resolve_routes(
                        db, app, routes_for(db, app.environment) if routes is None else routes
                    )
                    if not gateway_scope_service.enabled():
                        warnings = route_warnings
                else:
                    app.gateway_routes = []
                app.gateway_warnings = warnings
                _sync_oauth_clients(app, owner)
            else:
                _write_consumer(db, app, routes_for(db, app.environment) if routes is None else routes)
        _forget_elsewhere(app)
        app.gateway_status = str(GatewaySyncStatus.SYNCED)
        app.gateway_error = None
        app.gateway_synced_at = datetime.now(UTC)
    except AppError as exc:
        logger.warning("Gateway sync of app %s failed: %s", app.app_id, exc.message)
        app.gateway_status = str(GatewaySyncStatus.FAILED)
        app.gateway_error = exc.message[:2000]
    db.commit()
    return app


def oauth_clients() -> bool:
    """Every app key is also a Keycloak OAuth client (GATEWAY_PARTNER_AUTH=oauth)."""
    return settings.GATEWAY_PARTNER_AUTH == "oauth"


def needs_routes() -> bool:
    """Whether app sync needs the gateway's routes: the key modes (consumer whitelists)
    and oauth tokens that still carry route ids. Scopes alone need none."""
    if not oauth_clients():
        return True
    return not gateway_scope_service.enabled() or settings.GATEWAY_LEGACY_ROUTE_CLAIM


def _production_jwks(app: ParticipantApp, owner: Participant) -> dict | None:
    """The JWKS a production app client checks client assertions with
    (KEYCLOAK_PROD_CLIENT_AUTH=private-key-jwt): the owner's registered signing key.
    None = the client uses its secret."""
    if not is_production(app) or settings.KEYCLOAK_PROD_CLIENT_AUTH != "private-key-jwt":
        return None
    from app.services.partner_portal_service import public_jwk

    key = public_jwk(owner.public_key) if owner.public_key else None
    if key is None:
        raise ValidationError(
            "Production app keys use private_key_jwt (KEYCLOAK_PROD_CLIENT_AUTH), but the partner has no "
            "usable signing key (RSA >= 2048, EC P-256/P-384 or Ed25519). Ask them to send it with the "
            "production request."
        )
    return {"keys": [key]}


def is_production(app: ParticipantApp) -> bool:
    return str(app.environment).upper() == str(Environment.PRODUCTION)


def _sync_oauth_clients(app: ParticipantApp, owner: Participant | None) -> None:
    """One Keycloak confidential client per active key (client_id = API key, secret = API
    secret) in the app's environment's realm; its token names the owner, the app, the
    app's environment and the routes of the app's products (the same list as the
    consumer's whitelist). ``owner`` None: every client of the app goes."""
    # What a consumer held in the app-key modes travels in the token: the routes read it.
    per_minute, per_day = effective_limits(app) if settings.GATEWAY_RATE_LIMIT_ENABLED else (None, None)
    jwks = _production_jwks(app, owner) if owner is not None else None
    for credential in app.credentials:
        api_key = crypto.decrypt(credential.api_key_encrypted)
        if owner is None or not credential_is_live(credential):
            keycloak.delete_app_client(api_key)
            continue
        keycloak.upsert_app_client(
            api_key,
            crypto.decrypt(credential.api_secret_encrypted),
            str(app.unique_id),
            f"OAN sandbox app '{app.name}' (participant {app.participant_id}), key {credential.api_key_prefix}",
            {
                "participant_uid": str(owner.unique_id),
                "oan_app": str(app.unique_id),
                "oan_environments": [str(app.environment).lower()],
                # Route ids only while the gateway may still check them (legacy).
                **({"oan_routes": list(app.gateway_routes or [])} if needs_routes() else {}),
                # Always written, so a cleared whitelist or limit also clears the claim:
                # an empty list = any address, "0" = no limit of its own.
                "oan_ips": list(app.allowed_ips or []),
                "oan_limit_minute": str(per_minute or 0),
                "oan_limit_day": str(per_day or 0),
            },
            scopes=list(app.gateway_scopes or []),
            audience=settings.GATEWAY_TOKEN_AUDIENCE,
            jwks=jwks,
        )


def _forget_elsewhere(app: ParticipantApp) -> None:
    """An app's clients live only in its own realm (``keycloak.realm_for``): copies left in
    another one - written before KEYCLOAK_APPS_REALM or production's own Keycloak were set
    - are removed. In the key modes a production app's consumer leaves the main gateway
    once production has its own. Best effort."""
    if oauth_clients():
        home = keycloak.realm_for(app.environment)
        for realm in keycloak.app_realms():
            if keycloak.same_realm(realm, home):
                continue
            try:
                with keycloak.use_realm(realm):
                    _sync_oauth_clients(app, None)
            except AppError as exc:
                logger.warning("Old copy of app %s in realm %s not removed: %s", app.app_id, realm.name, exc.message)
    elif is_production(app) and gateway.separate_production() and app.gateway_consumer:
        try:
            with gateway.use_target(gateway.main_target()):
                gateway.delete_consumer(app.gateway_consumer)
        except AppError as exc:
            logger.warning("Old copy of production app %s not removed: %s", app.app_id, exc.message)


def owner_active(participant: Participant | None, environment: str = str(Environment.UAT)) -> bool:
    """Whether the participant may hold working keys in ``environment`` (else their
    clients / consumers there are removed)."""
    active = bool(
        participant is not None
        and not participant.is_deleted
        and participant.is_enabled
        and participant.is_uat_approved
        and not participant.is_rejected
    )
    if str(environment).upper() == str(Environment.PRODUCTION):
        return active and production_access(participant)
    return active


def production_access(participant: Participant) -> bool:
    """Approved for production and not switched off (as try-it and Keycloak roles read it)."""
    return bool(participant.is_prod_approved and participant.is_prod_enabled)


def sync_participant_apps(db: Session, participant_id: int) -> None:
    """Re-sync every app of a participant after their account state changed.

    Disabling, deleting or rejecting the participant removes the consumers
    from the gateway (their keys stop working at once); enabling or approving
    again puts them back.
    """
    apps = db.execute(
        select(ParticipantApp).where(
            ParticipantApp.participant_id == participant_id,
            ParticipantApp.is_deleted.is_(False),
        )
    ).scalars().all()
    sync_apps(db, apps)


def sync_apps(db: Session, apps: Iterable[ParticipantApp]) -> None:
    apps = list(apps)
    if not apps:
        return
    try:
        _sync_apps(db, apps)
    finally:
        for participant_id in sorted({app.participant_id for app in apps}):
            pm_policy_service.sync_participant(db, participant_id)


def _sync_apps(db: Session, apps: list[ParticipantApp]) -> None:
    if not gateway.app_sync_configured():
        for app in apps:
            sync_app(db, app, policies=False)
        return
    if not needs_routes():
        # Scopes only: nothing to read from any gateway.
        for app in apps:
            sync_app(db, app, [], policies=False)
        return
    # The routes of each gateway, read once; an unreachable one fails its apps only.
    routes: dict[gateway.AdminTarget, list[gateway.GatewayRoute] | AppError] = {}
    for app in apps:
        target = gateway.target_for(app.environment)
        if target not in routes:
            try:
                routes[target] = routes_for(db, app.environment)
            except AppError as exc:
                routes[target] = exc
        found = routes[target]
        if isinstance(found, AppError):
            app.gateway_status, app.gateway_error = str(GatewaySyncStatus.FAILED), found.message
            db.commit()
            continue
        sync_app(db, app, found, policies=False)


# ------------------------------------------------------- routes of the last pull
_ROUTE_FIELDS = {f.name for f in dataclasses.fields(gateway.GatewayRoute)}


def save_routes(
    db: Session, environment: str, gateway_type: str, routes: list[gateway.GatewayRoute], pulled_by: str
) -> None:
    """Keep the routes a pull read from the gateway ``environment`` ("UAT" / "PRODUCTION")."""
    row = db.get(GatewayRouteSnapshot, environment) or GatewayRouteSnapshot(environment=environment)
    row.gateway_type = gateway_type
    row.routes = [dataclasses.asdict(route) for route in routes]
    row.pulled_date = datetime.now(UTC)
    row.pulled_by = pulled_by[:200]
    db.add(row)
    db.commit()


def stored_routes(db: Session, environment: str) -> list[gateway.GatewayRoute] | None:
    """The routes of the last pull of that gateway; None when it was never pulled."""
    row = db.get(GatewayRouteSnapshot, environment)
    if row is None:
        return None
    return [
        gateway.GatewayRoute(**{k: v for k, v in item.items() if k in _ROUTE_FIELDS})
        for item in row.routes or []
    ]


def last_pull(db: Session, environment: str) -> datetime | None:
    row = db.get(GatewayRouteSnapshot, environment)
    if row is None or row.pulled_date is None:
        return None
    pulled = row.pulled_date
    return pulled.replace(tzinfo=UTC) if pulled.tzinfo is None else pulled


def routes_for(db: Session, environment: str) -> list[gateway.GatewayRoute]:
    """The routes of the gateway serving an app of ``environment``: the last pull's copy,
    else (never pulled) read from its Admin API."""
    target = gateway.target_for(environment)
    stored = stored_routes(db, target.environment)
    if stored is not None:
        return stored
    with gateway.use_target(target):
        return gateway.list_routes()


def resync_after_pull(db: Session, environment: str) -> int:
    """Re-sync the active apps on gateway ``environment`` whose route ids (or warnings)
    differ from what the pulled routes give, e.g. a renamed route with a new id.
    Returns how many were re-synced."""
    if not gateway.app_sync_configured() or not needs_routes():
        return 0
    routes = stored_routes(db, environment)
    if routes is None:
        return 0
    apps = db.execute(
        select(ParticipantApp).where(
            ParticipantApp.is_deleted.is_(False),
            ParticipantApp.status == int(AppStatus.ACTIVE),
        )
    ).scalars().all()
    changed = 0
    for app in apps:
        if gateway.target_for(app.environment).environment != environment:
            continue
        if not owner_active(db.get(Participant, app.participant_id), app.environment):
            continue
        route_ids, warnings = resolve_routes(db, app, routes)
        if route_ids == sorted(app.gateway_routes or []) and warnings == list(app.gateway_warnings or []):
            continue
        sync_app(db, app, routes, policies=False)
        changed += 1
    return changed


def _write_consumer(db: Session, app: ParticipantApp, routes: list[gateway.GatewayRoute]) -> None:
    username = app.gateway_consumer or consumer_name(app)
    app.gateway_consumer = username
    route_ids, warnings = resolve_routes(db, app, routes)
    owner = db.get(Participant, app.participant_id)
    gateway.put_consumer(
        username,
        f"OAN sandbox app '{app.name}' (participant {app.participant_id})",
        {
            "app_uid": str(app.unique_id),
            "participant_id": str(app.participant_id),
            # The owner as its Keycloak token names it (claim participant_uid): a gateway
            # that also checks partner tokens lets the key in only with its owner's token.
            "participant_uid": str(owner.unique_id),
            "environment": str(app.environment).lower(),
        },
        consumer_plugins(app, route_ids, warnings),
    )

    wanted: set[str] = set()
    for credential in app.credentials:
        if not credential_is_live(credential):
            continue
        key_id, hmac_id = credential_ids(credential)
        api_key = crypto.decrypt(credential.api_key_encrypted)
        description = f"{app.name}: key {credential.api_key_prefix}"
        gateway.put_credential(username, key_id, description, {"key-auth": {"key": api_key}})
        gateway.put_credential(
            username,
            hmac_id,
            description,
            {
                "hmac-auth": {
                    "key_id": api_key,
                    "secret_key": crypto.decrypt(credential.api_secret_encrypted),
                }
            },
        )
        wanted.update((key_id, hmac_id))
    for existing in gateway.list_credential_ids(username):
        if existing not in wanted:
            gateway.delete_credential(username, existing)

    app.gateway_routes = route_ids
    app.gateway_warnings = warnings


def consumer_plugins(
    app: ParticipantApp, route_ids: list[str], warnings: list[str]
) -> dict[str, dict]:
    """The consumer's plugins; problems with optional ones go to ``warnings``."""
    plugins: dict[str, dict] = {
        "consumer-restriction": {
            "type": "route_id",
            "whitelist": route_ids or [NO_ROUTE],
            "rejected_code": 403,
            "rejected_msg": REJECTED_MESSAGE,
        }
    }
    if app.allowed_ips:
        plugins["ip-restriction"] = {
            "whitelist": list(app.allowed_ips),
            "message": IP_REJECTED_MESSAGE,
        }
    limit = _limit_count(app, warnings)
    if limit:
        plugins["limit-count"] = limit
    logger_plugin = _http_logger(warnings)
    if logger_plugin:
        plugins["http-logger"] = logger_plugin
    return plugins


def effective_limits(app: ParticipantApp) -> tuple[int | None, int | None]:
    """(per minute, per day) for the app: the most generous of its approved products.

    A product without a value means no limit for that window, so one such
    product lifts it. No approved product: no limit (the app reaches nothing).
    """
    products = [
        s.api_product
        for s in app.subscriptions
        if s.status == int(SubscriptionStatus.APPROVED) and not s.api_product.is_deleted
    ]
    if not products:
        return None, None

    def most(values: list[int | None]) -> int | None:
        return None if any(v is None for v in values) else max(v for v in values if v is not None)

    return (
        most([p.rate_limit_per_minute for p in products]),
        most([p.quota_per_day for p in products]),
    )


def _limit_count(app: ParticipantApp, warnings: list[str]) -> dict | None:
    if not settings.GATEWAY_RATE_LIMIT_ENABLED:
        return None
    per_minute, per_day = effective_limits(app)
    rules = []
    if per_minute:
        rules.append({"count": per_minute, "time_window": 60, "key": "${consumer_name} minute", "header_prefix": "Minute"})
    if per_day:
        rules.append({"count": per_day, "time_window": 86400, "key": "${consumer_name} day", "header_prefix": "Day"})
    if not rules:
        return None
    plugin: dict = {
        "rules": rules,
        "rejected_code": 429,
        "rejected_msg": RATE_LIMIT_MESSAGE,
        "policy": "local",
    }
    if settings.GATEWAY_RATE_LIMIT_POLICY == "redis":
        if settings.GATEWAY_RATE_LIMIT_REDIS_HOST:
            plugin.update(
                policy="redis",
                redis_host=settings.GATEWAY_RATE_LIMIT_REDIS_HOST,
                redis_port=settings.GATEWAY_RATE_LIMIT_REDIS_PORT,
            )
            if settings.GATEWAY_RATE_LIMIT_REDIS_PASSWORD:
                plugin["redis_password"] = settings.GATEWAY_RATE_LIMIT_REDIS_PASSWORD
        else:
            warnings.append("GATEWAY_RATE_LIMIT_REDIS_HOST is empty: limits are counted per gateway node.")
    return plugin


def _http_logger(warnings: list[str]) -> dict | None:
    if not settings.GATEWAY_LOG_INGEST_ENABLED:
        return None
    if not settings.GATEWAY_LOG_INGEST_URL or not settings.GATEWAY_LOG_INGEST_TOKEN:
        warnings.append(
            "Gateway logs are on but GATEWAY_LOG_INGEST_URL / GATEWAY_LOG_INGEST_TOKEN are empty:"
            " direct calls are not reported."
        )
        return None
    return {
        "uri": settings.GATEWAY_LOG_INGEST_URL,
        "auth_header": f"Bearer {settings.GATEWAY_LOG_INGEST_TOKEN}",
        "batch_max_size": 100,
        "inactive_timeout": settings.GATEWAY_LOG_FLUSH_SECONDS,
        "timeout": 5,
        "log_format": LOG_FORMAT,
    }


def resolve_routes(
    db: Session, app: ParticipantApp, routes: list[gateway.GatewayRoute]
) -> tuple[list[str], list[str]]:
    """Route ids the app's approved products fully cover, and what could not be granted."""
    approved = [
        s.api_product_id
        for s in app.subscriptions
        if s.status == int(SubscriptionStatus.APPROVED)
    ]
    endpoint_ids = sorted(
        {eid for ids in ApiProductRepository(db).endpoint_ids(approved).values() for eid in ids}
    )
    granted: dict[tuple[str, str], Endpoint] = {}
    if endpoint_ids:
        # Only endpoints called through the gateway; one with its own upstream
        # URL never reaches it.
        stmt = (
            select(Endpoint)
            .join(Product, Product.product_id == Endpoint.product_id)
            .where(
                Endpoint.endpoint_id.in_(endpoint_ids),
                or_(Endpoint.is_gateway_published.is_(True), Product.is_gateway_published.is_(True)),
            )
        )
        for endpoint in db.execute(stmt).scalars():
            granted[gateway.operation_key(endpoint.method, endpoint.endpoint_url)] = endpoint

    route_ids: list[str] = []
    warnings: list[str] = []
    served: set[tuple[str, str]] = set()
    for route in routes:
        if not route.id:
            continue
        methods = route.methods or list(gateway.OPERATION_METHODS)
        operations = {gateway.operation_key(m, p) for p in route.paths for m in methods}
        if not operations:
            continue
        covered = operations & granted.keys()
        served |= covered
        if not covered:
            continue
        if covered == operations:
            route_ids.append(route.id)
        else:
            warnings.append(
                f"Route '{route.name}' also serves {len(operations - covered)} operation(s) outside"
                f" this app's products, so it is not granted; split the route per operation."
            )
    for key, endpoint in sorted(granted.items()):
        if key not in served:
            warnings.append(f"{key[0]} {endpoint.endpoint_url}: no gateway route serves it.")
    return sorted(route_ids), warnings
