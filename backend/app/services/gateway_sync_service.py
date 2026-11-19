"""Pull the API gateway's routes into the catalogue ("Pull from gateway").

Every route operation (method + path) the gateway serves is matched against the
end-points already flagged "served through the API gateway":

* matched: the end-point is kept and only filled in where the gateway knows
  more (gateway flag, missing name / description, path parameters, the
  credential header) - an imported OpenAPI contract is never overwritten;
* new: it is created, unpublished, in the product already holding the
  service's end-point with the closest path, else in the product of its
  gateway service (created on first sight, keyed by ``Product.gateway_product_id``);
* gateway end-points the gateway no longer serves are reported, not deleted.

``dry_run`` computes the same report and rolls everything back, so the console
can show what a pull would change before it is applied.

A real pull also keeps the routes it read (``GatewayRouteSnapshot``, one per
gateway) and re-syncs the active apps whose granted route ids changed, e.g.
because a route was renamed and got a new id. App sync then resolves route ids
from that copy, so after a pull the sandbox needs nothing from the Admin API to
approve apps or change products. ``auto_pull`` runs the same pull without an
administrator every GATEWAY_AUTO_PULL_HOURS (``main``). ``environment``
PRODUCTION reads production's own gateway (GATEWAY_PROD_ADMIN_URL) when it has
one; the catalogue is shared, so its routes match the same end-points.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.deps import AdminPrincipal
from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.integrations import gateway
from app.models.catalog import Endpoint, Product
from app.models.enums import Environment
from app.repositories.catalog_repository import ProductRepository
from app.services import app_gateway_service, audit_service
from app.services.audit_service import Action

logger = get_logger(__name__)

#: Shown as the author of an automatic pull.
AUTOMATIC = "automatic"
#: pg_try_advisory_lock key: one automatic pull at a time across API replicas.
_AUTO_PULL_LOCK = 7_340_211_801

#: Rows listed per section of the report; the counts are always complete.
REPORT_LIMIT = 200

_PATH_PARAM = re.compile(r"\{([^}]+)\}")


def status() -> dict[str, Any]:
    return {
        "enabled": settings.GATEWAY_SYNC_ENABLED,
        "gateway_type": settings.GATEWAY_TYPE,
        "admin_url_configured": bool(settings.GATEWAY_ADMIN_URL),
        #: Gateways the console can pull from: UAT, plus PRODUCTION when it has its own.
        "environments": [str(Environment.UAT)]
        + ([str(Environment.PRODUCTION)] if gateway.separate_production() else []),
    }


def sync(
    db: Session,
    admin: AdminPrincipal | None,
    dry_run: bool = False,
    environment: Environment = Environment.UAT,
) -> dict[str, Any]:
    """Pull one gateway into the catalogue. ``admin`` None: an automatic pull."""
    target = gateway.target_for(environment)
    with gateway.use_target(target):
        snapshot = gateway.fetch()
    services = {service.key: service for service in snapshot.services}

    report: dict[str, Any] = {
        "gateway_type": snapshot.gateway_type,
        "environment": str(environment),
        "dry_run": dry_run,
        "services": len(snapshot.services),
        "routes": len(snapshot.routes),
        "operations": 0,
        "products_created": [],
        "created": [],
        "updated": [],
        "unchanged": 0,
        "skipped": [],
        "missing": [],
        "apps_resynced": 0,
    }

    existing = _gateway_endpoints(db)
    by_route = {_route_key(e.method, e.endpoint_url): e for e in existing}
    products_by_key = _products_by_gateway_key(db)
    # Where each gateway service's routes already live in the catalogue, for
    # services whose products predate the sync (e.g. A2C, split by domain).
    placed: dict[str, list[tuple[str, int]]] = {}
    for route in snapshot.routes:
        for path in route.paths:
            for method in route.methods:
                endpoint = by_route.get(_route_key(method, path))
                if endpoint is not None and route.service_key:
                    placed.setdefault(route.service_key, []).append((path, endpoint.product_id))
    seen: set[tuple[str, str]] = set()

    for route in snapshot.routes:
        methods = [m for m in route.methods if m in gateway.OPERATION_METHODS]
        if not methods:
            # e.g. a CORS preflight (OPTIONS) route: one row, not one per path.
            report["skipped"].append(
                {
                    "route": route.name,
                    "path": ", ".join((route.paths + route.skipped)[:3])
                    + (" …" if len(route.paths + route.skipped) > 3 else ""),
                    "reason": "No API method (" + (", ".join(route.methods) or "any method") + ")",
                }
            )
            continue
        for raw in route.skipped:
            report["skipped"].append(
                {"route": route.name, "path": raw, "reason": "Wildcard or regex path, not one operation"}
            )
        for path in route.paths:
            for method in methods:
                key = _route_key(method, path)
                if key in seen:
                    continue
                seen.add(key)
                report["operations"] += 1
                endpoint = by_route.get(key)
                if endpoint is not None:
                    changes = _refresh(endpoint, route, path, admin)
                    if changes:
                        report["updated"].append(_row(endpoint, method, path, changes))
                    else:
                        report["unchanged"] += 1
                    continue

                product = products_by_key.get(route.service_key or "") or _nearest_product(
                    db, placed.get(route.service_key or "", []), path
                )
                if product is None:
                    product = _create_product(db, admin, services.get(route.service_key or ""), route)
                    products_by_key[route.service_key or ""] = product
                    report["products_created"].append(
                        {"product_id": product.product_id, "product_name": product.product_name}
                    )
                endpoint = _create_endpoint(db, admin, product, route, method, path)
                by_route[key] = endpoint
                report["created"].append(_row(endpoint, method, path, []))

    for endpoint in existing:
        if _route_key(endpoint.method, endpoint.endpoint_url) not in seen:
            report["missing"].append(_row(endpoint, endpoint.method, endpoint.endpoint_url, []))

    if dry_run:
        db.rollback()
        # Rows created in the preview were rolled back: their ids do not exist.
        new_products = {p["product_id"] for p in report["products_created"]}
        for row in report["created"] + report["products_created"]:
            row.pop("endpoint_id", None)
            if row["product_id"] in new_products:
                row["product_id"] = None
    else:
        db.commit()
        app_gateway_service.save_routes(
            db, target.environment, snapshot.gateway_type, snapshot.routes, _actor_name(admin)
        )
        report["apps_resynced"] = app_gateway_service.resync_after_pull(db, target.environment)
        description = (
            f"{'Automatic pull' if admin is None else 'Pulled'} from {snapshot.gateway_type}"
            f"{' (production gateway)' if environment == Environment.PRODUCTION else ''}: "
            f"{len(report['created'])} created, "
            f"{len(report['updated'])} updated, {report['unchanged']} unchanged, "
            f"{len(report['missing'])} not on the gateway, "
            f"{report['apps_resynced']} app(s) re-synced"
        )
        if admin is None:
            audit_service.record(
                db, Action.GATEWAY_SYNC, actor_name=AUTOMATIC, entity="product",
                description=description, country_code=settings.DEFAULT_COUNTRY_CODE,
            )
        else:
            audit_service.record_admin(db, admin, Action.GATEWAY_SYNC, entity="product", description=description)

    for section in ("created", "updated", "skipped", "missing"):
        report[f"{section}_count"] = len(report[section])
        report[section] = report[section][:REPORT_LIMIT]
    return report


def auto_pull(db: Session) -> list[dict[str, Any]]:
    """Pull every gateway the console can pull from, without an administrator.

    Skipped when pulling is off, or when another replica holds the lock or pulled
    less than GATEWAY_AUTO_PULL_HOURS ago (so restarts and several pods pull once).
    One gateway failing does not stop the others; returns one summary per gateway.
    """
    if not settings.GATEWAY_SYNC_ENABLED or settings.GATEWAY_AUTO_PULL_HOURS <= 0:
        return []
    postgres = db.get_bind().dialect.name == "postgresql"
    if postgres and not db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _AUTO_PULL_LOCK}).scalar():
        return []
    try:
        summaries = []
        # Pulled a little early still counts, so a pod restarted just before the mark waits.
        due = timedelta(hours=settings.GATEWAY_AUTO_PULL_HOURS) - timedelta(minutes=5)
        for name in status()["environments"]:
            environment = Environment(name)
            pulled = app_gateway_service.last_pull(db, gateway.target_for(environment).environment)
            if pulled is not None and datetime.now(UTC) - pulled < due:
                continue
            try:
                report = sync(db, None, environment=environment)
            except AppError as exc:
                db.rollback()
                logger.warning("Automatic pull of the %s gateway failed: %s", name, exc.message)
                summaries.append({"environment": name, "error": exc.message})
                continue
            summaries.append({
                "environment": name,
                **{k: report[f"{k}_count"] for k in ("created", "updated", "missing")},
                "apps_resynced": report["apps_resynced"],
            })
        return summaries
    finally:
        if postgres:
            db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _AUTO_PULL_LOCK})
            db.commit()


# ---------------------------------------------------------------- helpers
_route_key = gateway.operation_key


def _actor_name(admin: AdminPrincipal | None) -> str:
    if admin is None:
        return AUTOMATIC
    return admin.user.full_name or admin.user.login_name or str(admin.id)


def _actor_id(admin: AdminPrincipal | None) -> int | None:
    return admin.id if admin is not None else None


def _gateway_endpoints(db: Session) -> list[Endpoint]:
    stmt = (
        select(Endpoint)
        .join(Product, Product.product_id == Endpoint.product_id)
        .where(
            Endpoint.is_deleted.is_(False),
            Product.is_deleted.is_(False),
            or_(Endpoint.is_gateway_published.is_(True), Product.is_gateway_published.is_(True)),
        )
        .order_by(Endpoint.endpoint_id)
    )
    return list(db.execute(stmt).scalars())


def _products_by_gateway_key(db: Session) -> dict[str, Product]:
    stmt = select(Product).where(
        Product.is_deleted.is_(False), Product.gateway_product_id.is_not(None)
    )
    return {p.gateway_product_id: p for p in db.execute(stmt).scalars()}


def _nearest_product(db: Session, placed: list[tuple[str, int]], path: str) -> Product | None:
    """The product holding the service's end-point whose path shares the most leading segments."""
    segments = path.strip("/").split("/")
    best_id, best_score = None, 0
    for other, product_id in placed:
        score = 0
        for mine, theirs in zip(segments, other.strip("/").split("/"), strict=False):
            if mine != theirs:
                break
            score += 1
        if score > best_score:
            best_id, best_score = product_id, score
    return db.get(Product, best_id) if best_id is not None else None


def _create_product(
    db: Session,
    admin: AdminPrincipal | None,
    service: gateway.GatewayService | None,
    route: gateway.GatewayRoute,
) -> Product:
    repo = ProductRepository(db)
    base = service.name if service else "gateway-routes"
    name, suffix = base, 2
    while repo.name_taken(name):
        name, suffix = f"{base}-{suffix}", suffix + 1
    return repo.create(
        commit=False,
        product_name=name,
        display_name=_title(base),
        description=(service.description if service else None)
        or f"Pulled from the {settings.GATEWAY_TYPE} gateway. Review, then publish.",
        country_code=(admin.country_code if admin is not None else None) or settings.DEFAULT_COUNTRY_CODE,
        is_gateway_published=True,
        is_published=False,
        gateway_product_id=route.service_key or "",
        added_by=_actor_id(admin),
        modify_by=_actor_id(admin),
    )


def _create_endpoint(
    db: Session,
    admin: AdminPrincipal | None,
    product: Product,
    route: gateway.GatewayRoute,
    method: str,
    path: str,
) -> Endpoint:
    endpoint = Endpoint(
        product_id=product.product_id,
        display_name=f"{method} {path}",
        description=route.description,
        endpoint_url=path,
        method=method,
        path_params=_path_params(path, {}),
        query_params={},
        header_params=_auth_params(route, {}),
        country_code=product.country_code,
        is_gateway_published=True,
        is_published=False,
        api_keywords=[],
        added_by=_actor_id(admin),
        modify_by=_actor_id(admin),
    )
    db.add(endpoint)
    db.flush()
    return endpoint


def _refresh(
    endpoint: Endpoint, route: gateway.GatewayRoute, path: str, admin: AdminPrincipal | None
) -> list[str]:
    """Fill in what the gateway knows and the end-point lacks; never overwrite."""
    # Matched end-points are already served through the gateway (on themselves
    # or their product), so the flag is not touched.
    changes: list[str] = []
    if not endpoint.display_name:
        endpoint.display_name = f"{endpoint.method} {path}"
        changes.append("name")
    if not endpoint.description and route.description:
        endpoint.description = route.description
        changes.append("description")
    path_params = _path_params(endpoint.endpoint_url or path, endpoint.path_params or {})
    if path_params != (endpoint.path_params or {}):
        endpoint.path_params = path_params
        changes.append("path parameters")
    header_params = _auth_params(route, endpoint.header_params or {})
    if header_params != (endpoint.header_params or {}):
        added = [k for k in header_params if k not in (endpoint.header_params or {})]
        endpoint.header_params = header_params
        changes.append(f"{', '.join(added)} header{'s' if len(added) > 1 else ''}")
    if changes:
        endpoint.modify_by = _actor_id(admin)
    return changes


def _path_params(path: str, current: dict[str, Any]) -> dict[str, Any]:
    params = dict(current)
    for name in _PATH_PARAM.findall(path):
        params.setdefault(name, {"required": True, "schema": {"type": "string"}, "description": None})
    return params


def _auth_params(route: gateway.GatewayRoute, current: dict[str, Any]) -> dict[str, Any]:
    """The credential headers the route checks: its auth header and the app key."""
    params = dict(current)
    wanted = [(route.auth_header, route.auth_hint)]
    if route.key_header:
        wanted.append((route.key_header, "<app API key from My Apps>"))
    for header, hint in wanted:
        if header and not any(k.lower() == header.lower() for k in params):
            params[header] = {
                "required": True,
                "schema": {"type": "string"},
                "description": f"{hint} - checked by the API gateway",
            }
    return params


def _row(endpoint: Endpoint, method: str | None, path: str | None, changes: list[str]) -> dict:
    row = {
        "endpoint_id": endpoint.endpoint_id,
        "product_id": endpoint.product_id,
        "product_name": endpoint.product.display_name or endpoint.product.product_name,
        "method": (method or "").upper(),
        "path": path,
    }
    if changes:
        row["changes"] = changes
    return row


def _title(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip().title()
