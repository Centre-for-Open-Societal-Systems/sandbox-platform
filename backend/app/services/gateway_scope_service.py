"""OAuth scopes of the partner APIs: which scope a gateway end-point needs, and which
scopes an app's approved API products give it.

The scope of every route is set by the gateway's Helm chart (``apis.yaml``), and the
sandbox gets the same map as GATEWAY_SCOPES (the chart's ``gateway-scopes.json``):

* ``"METHOD /gateway/path"`` - one operation with its own scope (exact match, path
  parameter names ignored), else
* ``"/gateway-prefix"`` - every path under that prefix, by whole segments (the
  longest prefix wins: "/consent-manager" does not cover "/consent-manager-partner/x").

An app's scopes are the scopes of the gateway end-points of its approved API
products; Keycloak puts them in the token's standard ``scope`` claim. Nothing here
reads the gateway: the map is configuration, the end-points are the catalogue.

A scope opens every route that requires it. An API product holding only some of a
scope's end-points therefore grants more than it lists; ``product_scopes`` reports
that so the console can warn.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.integrations import gateway
from app.models.app import ParticipantApp
from app.models.catalog import Endpoint, Product
from app.models.enums import SubscriptionStatus
from app.repositories.app_repository import ApiProductRepository


def enabled() -> bool:
    """Scopes are in use: oauth mode with a scope map."""
    return settings.GATEWAY_PARTNER_AUTH == "oauth" and bool(settings.gateway_scopes)


def scope_for(method: str | None, path: str | None) -> str | None:
    """The scope a gateway operation needs; None when the map does not cover it."""
    scopes = settings.gateway_scopes
    if not scopes or not path:
        return None
    wanted = gateway.operation_key(method, path)
    prefixes: list[tuple[int, str]] = []
    for key, scope in scopes.items():
        verb, _, rest = key.partition(" ")
        if rest:  # "METHOD /path"
            if gateway.operation_key(verb, rest) == wanted:
                return scope
            continue
        prefix = key.rstrip("/")
        if wanted[1] == (prefix or "/") or wanted[1].startswith(prefix + "/"):
            prefixes.append((len(prefix), scope))
    return max(prefixes)[1] if prefixes else None


def _gateway_endpoints(db: Session, endpoint_ids: list[int] | None = None) -> list[Endpoint]:
    """End-points served through the gateway (on themselves or their product)."""
    stmt = (
        select(Endpoint)
        .join(Product, Product.product_id == Endpoint.product_id)
        .where(
            Endpoint.is_deleted.is_(False),
            Product.is_deleted.is_(False),
            or_(Endpoint.is_gateway_published.is_(True), Product.is_gateway_published.is_(True)),
        )
    )
    if endpoint_ids is not None:
        if not endpoint_ids:
            return []
        stmt = stmt.where(Endpoint.endpoint_id.in_(endpoint_ids))
    return list(db.execute(stmt).scalars())


def app_scopes(db: Session, app: ParticipantApp) -> tuple[list[str], list[str]]:
    """(scopes, warnings) of an app: the scopes of its approved products' gateway
    end-points, and the end-points no scope covers (they stay closed to the app)."""
    approved = [s.api_product_id for s in app.subscriptions if s.status == int(SubscriptionStatus.APPROVED)]
    ids = sorted({e for ids in ApiProductRepository(db).endpoint_ids(approved).values() for e in ids})
    scopes: set[str] = set()
    warnings: list[str] = []
    for endpoint in sorted(_gateway_endpoints(db, ids), key=lambda e: (e.endpoint_url or "", e.method or "")):
        scope = scope_for(endpoint.method, endpoint.endpoint_url)
        if scope:
            scopes.add(scope)
        else:
            warnings.append(
                f"{(endpoint.method or '').upper()} {endpoint.endpoint_url}: no gateway scope covers it "
                "(GATEWAY_SCOPES), so this app cannot call it."
            )
    return sorted(scopes), warnings


def product_scopes(db: Session, api_product_id: int) -> list[dict]:
    """The scopes an API product grants, each with how many of its gateway end-points
    the product holds (``in_product``) out of all (``total``): fewer means the product
    opens end-points it does not list."""
    if not enabled():
        return []
    ids = ApiProductRepository(db).endpoint_ids([api_product_id]).get(api_product_id, [])
    in_product: dict[str, int] = {}
    for endpoint in _gateway_endpoints(db, ids):
        scope = scope_for(endpoint.method, endpoint.endpoint_url)
        if scope:
            in_product[scope] = in_product.get(scope, 0) + 1
    if not in_product:
        return []
    totals: dict[str, int] = {}
    for endpoint in _gateway_endpoints(db):
        scope = scope_for(endpoint.method, endpoint.endpoint_url)
        if scope in in_product:
            totals[scope] = totals.get(scope, 0) + 1
    return [
        {"scope": scope, "in_product": count, "total": totals.get(scope, count),
         "whole_api": count >= totals.get(scope, count)}
        for scope, count in sorted(in_product.items())
    ]
