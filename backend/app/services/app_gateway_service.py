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
check the app's Keycloak token, so the sandbox only reads the routes (a viewer
admin key is enough) and puts the granted route ids in the token's
``oan_routes``; each active key is a Keycloak client instead. The per-app
consumer plugins above (IP whitelist, per-product limits, http-logger) do not
apply then; the routes limit calls per app themselves.

``sync_app`` is idempotent and never raises: a gateway failure is stored on
the app (``gateway_status`` FAILED, ``gateway_error``) and can be retried.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core import crypto
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.integrations import gateway, keycloak
from app.models.app import ParticipantApp, ParticipantAppCredential
from app.models.catalog import Endpoint, Product
from app.models.enums import (
    AppStatus,
    CredentialStatus,
    GatewaySyncStatus,
    SubscriptionStatus,
)
from app.models.participant import Participant
from app.repositories.app_repository import ApiProductRepository

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


def credential_ids(credential: ParticipantAppCredential) -> tuple[str, str]:
    return f"{credential.unique_id}-key", f"{credential.unique_id}-hmac"


def sync_app(
    db: Session, app: ParticipantApp, routes: list[gateway.GatewayRoute] | None = None
) -> ParticipantApp:
    """Bring the gateway in line with ``app``; ``routes`` saves a fetch when syncing many."""
    if not gateway.app_sync_configured():
        app.gateway_status = str(GatewaySyncStatus.DISABLED)
        app.gateway_error = None
        db.commit()
        return app
    try:
        if app.is_deleted or app.status != int(AppStatus.ACTIVE) or not owner_active(
            db.get(Participant, app.participant_id)
        ):
            if oauth_clients():
                _sync_oauth_clients(app, None)
            elif app.gateway_consumer:
                gateway.delete_consumer(app.gateway_consumer)
            app.gateway_routes, app.gateway_warnings = [], []
        elif oauth_clients():
            # The routes check the token, not a consumer: only read the routes (their ids
            # go into the token's oan_routes), never write to the gateway.
            app.gateway_routes, app.gateway_warnings = resolve_routes(
                db, app, gateway.list_routes() if routes is None else routes
            )
            _sync_oauth_clients(app, db.get(Participant, app.participant_id))
        else:
            _write_consumer(db, app, gateway.list_routes() if routes is None else routes)
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


def _sync_oauth_clients(app: ParticipantApp, owner: Participant | None) -> None:
    """One Keycloak confidential client per active key (client_id = API key, secret = API
    secret); its token names the owner, the app, the approved environments and the routes
    of the app's products (the same list as the consumer's whitelist). ``owner`` None:
    every client of the app goes."""
    environments = []
    if owner is not None:
        if owner.is_uat_approved:
            environments.append("uat")
        if owner.is_prod_approved:
            environments.append("production")
    for credential in app.credentials:
        api_key = crypto.decrypt(credential.api_key_encrypted)
        if owner is None or credential.status != int(CredentialStatus.ACTIVE):
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
                "oan_environments": environments,
                "oan_routes": list(app.gateway_routes or []),
            },
        )


def owner_active(participant: Participant | None) -> bool:
    """Whether the participant may hold working keys (else their consumers are removed)."""
    return bool(
        participant is not None
        and not participant.is_deleted
        and participant.is_enabled
        and participant.is_uat_approved
        and not participant.is_rejected
    )


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
    routes = None
    if gateway.app_sync_configured():
        try:
            routes = gateway.list_routes()
        except AppError as exc:
            for app in apps:
                app.gateway_status, app.gateway_error = str(GatewaySyncStatus.FAILED), exc.message
            db.commit()
            return
    for app in apps:
        sync_app(db, app, routes)


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
        if credential.status != int(CredentialStatus.ACTIVE):
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
