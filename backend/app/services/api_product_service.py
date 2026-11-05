"""API products: the access bundles apps are granted (console "API Products").

Changing an API product's endpoints changes what its subscribed apps may
call, so every approved app is re-synced to the gateway afterwards.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AdminPrincipal
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page
from app.models.app import ApiProduct, ParticipantApp
from app.models.catalog import Endpoint, Product
from app.repositories.app_repository import ApiProductRepository
from app.repositories.catalog_repository import EndpointRepository
from app.schemas.app import (
    ApiProductCreate,
    ApiProductDetailOut,
    ApiProductEndpointOut,
    ApiProductListQuery,
    ApiProductOut,
    ApiProductUpdate,
)
from app.services import app_gateway_service, audit_service
from app.services.audit_service import Action


def list_products(db: Session, query: ApiProductListQuery) -> Page:
    repo = ApiProductRepository(db)
    stmt = repo.base_stmt()
    if query.is_published is not None:
        stmt = stmt.where(ApiProduct.is_published.is_(query.is_published))
    page = repo.paginate(
        query.page, query.limit, query.search, query.sort_by or "sort_order", query.sort_dir, stmt=stmt
    )
    page.rows = _summaries(db, page.rows)
    return page


def get_product(db: Session, api_product_id: int) -> ApiProductDetailOut:
    product = _require(db, api_product_id)
    summary = _summaries(db, [product])[0]
    return ApiProductDetailOut(
        **summary.model_dump(), endpoints=endpoint_rows(db, ApiProductRepository(db).endpoints(product.api_product_id))
    )


def create_product(db: Session, admin: AdminPrincipal, payload: ApiProductCreate) -> ApiProductDetailOut:
    repo = ApiProductRepository(db)
    if repo.name_taken(payload.name):
        raise ConflictError(f"An API product named '{payload.name}' already exists.")
    endpoint_ids = _valid_endpoint_ids(db, payload.endpoint_ids)
    product = ApiProduct(
        **payload.model_dump(exclude={"endpoint_ids", "approval_type"}),
        approval_type=str(payload.approval_type),
        added_by=admin.id,
        modify_by=admin.id,
    )
    db.add(product)
    db.flush()
    repo.replace_endpoints(product, endpoint_ids)
    db.commit()
    audit_service.record_admin(
        db, admin, Action.API_PRODUCT_CREATE, entity="api_product", entity_id=product.api_product_id,
        description=f"Created API product {product.name} with {len(endpoint_ids)} endpoint(s)",
    )
    return get_product(db, product.api_product_id)


def update_product(
    db: Session, admin: AdminPrincipal, api_product_id: int, payload: ApiProductUpdate
) -> ApiProductDetailOut:
    repo = ApiProductRepository(db)
    product = _require(db, api_product_id)
    if repo.name_taken(payload.name, exclude_id=api_product_id):
        raise ConflictError(f"An API product named '{payload.name}' already exists.")
    endpoint_ids = _valid_endpoint_ids(db, payload.endpoint_ids)
    before = {link.endpoint_id for link in product.endpoints}
    limits_before = (product.rate_limit_per_minute, product.quota_per_day)
    for key, value in payload.model_dump(exclude={"endpoint_ids", "approval_type"}).items():
        setattr(product, key, value)
    product.approval_type = str(payload.approval_type)
    product.modify_by = admin.id
    repo.replace_endpoints(product, endpoint_ids)
    db.commit()
    audit_service.record_admin(
        db, admin, Action.API_PRODUCT_UPDATE, entity="api_product", entity_id=api_product_id,
        description=f"Updated API product {product.name} ({len(endpoint_ids)} endpoint(s))",
    )
    # Apps hold the product's routes and limits on their gateway consumer.
    if before != set(endpoint_ids) or limits_before != (payload.rate_limit_per_minute, payload.quota_per_day):
        _resync_subscribers(db, api_product_id)
    return get_product(db, api_product_id)


def set_published(db: Session, admin: AdminPrincipal, api_product_id: int, is_published: bool) -> ApiProductOut:
    product = _require(db, api_product_id)
    product.is_published = is_published
    product.modify_by = admin.id
    db.commit()
    audit_service.record_admin(
        db, admin, Action.API_PRODUCT_PUBLISH, entity="api_product", entity_id=api_product_id,
        description=f"{'Published' if is_published else 'Unpublished'} API product {product.name}",
    )
    return _summaries(db, [product])[0]


def delete_product(db: Session, admin: AdminPrincipal, api_product_id: int) -> None:
    repo = ApiProductRepository(db)
    product = _require(db, api_product_id)
    if repo.subscriber_app_ids(api_product_id):
        raise ConflictError(
            "Apps still have access to this API product. Revoke their access first, or unpublish it."
        )
    repo.soft_delete(product, actor_id=admin.id)
    audit_service.record_admin(
        db, admin, Action.API_PRODUCT_DELETE, entity="api_product", entity_id=api_product_id,
        description=f"Deleted API product {product.name}",
    )


def endpoint_options(db: Session) -> list[dict[str, Any]]:
    """Every catalogue endpoint, grouped by catalogue product, for the endpoint picker."""
    stmt = (
        select(Endpoint, Product)
        .join(Product, Product.product_id == Endpoint.product_id)
        .where(Endpoint.is_deleted.is_(False), Product.is_deleted.is_(False))
        .order_by(Product.sort_order, Product.product_name, Endpoint.sort_order, Endpoint.endpoint_id)
    )
    groups: dict[int, dict[str, Any]] = {}
    for endpoint, product in db.execute(stmt):
        group = groups.setdefault(
            product.product_id,
            {
                "product_id": product.product_id,
                "product_name": product.display_name or product.product_name,
                "is_gateway_published": bool(product.is_gateway_published),
                "endpoints": [],
            },
        )
        group["endpoints"].append(
            {
                "endpoint_id": endpoint.endpoint_id,
                "display_name": endpoint.display_name,
                "method": endpoint.method,
                "endpoint_url": endpoint.endpoint_url,
                "is_published": bool(endpoint.is_published),
                "is_gateway_published": bool(endpoint.is_gateway_published or product.is_gateway_published),
            }
        )
    return list(groups.values())


def endpoint_rows(db: Session, endpoints: list[Endpoint]) -> list[ApiProductEndpointOut]:
    names = EndpointRepository(db).product_names(list({e.product_id for e in endpoints}))
    return [
        ApiProductEndpointOut(
            endpoint_id=e.endpoint_id,
            product_id=e.product_id,
            product_name=names.get(e.product_id),
            display_name=e.display_name,
            method=e.method,
            endpoint_url=e.endpoint_url,
        )
        for e in endpoints
    ]


# ---------------------------------------------------------------- helpers
def _require(db: Session, api_product_id: int) -> ApiProduct:
    product = ApiProductRepository(db).get(api_product_id)
    if product is None:
        raise NotFoundError("API product not found.")
    return product


def _valid_endpoint_ids(db: Session, endpoint_ids: list[int]) -> list[int]:
    ids = list(dict.fromkeys(endpoint_ids))
    if not ids:
        return []
    found = {e.endpoint_id for e in EndpointRepository(db).get_many(ids, include_deleted=False)}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValidationError(f"Unknown endpoint id(s): {', '.join(map(str, missing[:10]))}.")
    return ids


def _summaries(db: Session, products: list[ApiProduct]) -> list[ApiProductOut]:
    repo = ApiProductRepository(db)
    ids = [p.api_product_id for p in products]
    endpoint_ids = repo.endpoint_ids(ids)
    app_counts = repo.subscription_counts(ids)
    return [
        ApiProductOut.model_validate(p).model_copy(
            update={
                "endpoint_count": len(endpoint_ids.get(p.api_product_id, [])),
                "app_count": app_counts.get(p.api_product_id, 0),
            }
        )
        for p in products
    ]


def _resync_subscribers(db: Session, api_product_id: int) -> None:
    app_ids = ApiProductRepository(db).subscriber_app_ids(api_product_id)
    if not app_ids:
        return
    apps = db.execute(
        select(ParticipantApp).where(
            ParticipantApp.app_id.in_(app_ids), ParticipantApp.is_deleted.is_(False)
        )
    ).scalars()
    app_gateway_service.sync_apps(db, apps)
