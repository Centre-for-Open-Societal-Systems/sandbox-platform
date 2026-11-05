"""Console: API products (access bundles) and participant apps.

``/admin/api-products`` - define which endpoints each API product grants.
``/admin/apps``         - approve or reject new apps (approval issues the first
                          key), decide product requests, revoke apps, re-sync an
                          app to the gateway.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import AdminPrincipal, DbSession, require_permission
from app.core.permissions import Permission
from app.core.responses import ok
from app.core.status_codes import StatusCode
from app.models.enums import SubscriptionStatus
from app.schemas.app import (
    AdminAppListQuery,
    ApiProductCreate,
    ApiProductListQuery,
    ApiProductUpdate,
    AppRevokeRequest,
    SubscriptionDecision,
    SubscriptionReject,
)
from app.schemas.catalog import PublishRequest
from app.services import api_product_service, app_service

router = APIRouter(tags=["Admin / API Products & Apps"])

ManageProducts = Annotated[AdminPrincipal, Depends(require_permission(Permission.API_PRODUCTS))]
ManageApps = Annotated[AdminPrincipal, Depends(require_permission(Permission.PARTICIPANT_APPS))]


# ----------------------------------------------------------- API products
@router.post("/api-products/list")
def list_api_products(payload: ApiProductListQuery, admin: ManageProducts, db: DbSession):
    page = api_product_service.list_products(db, payload)
    page.rows = [row.model_dump() for row in page.rows]
    return ok("API products loaded.", page.as_dict("api_products"))


@router.get("/api-products/endpoint-options")
def endpoint_options(admin: ManageProducts, db: DbSession):
    """Catalogue endpoints grouped by catalogue product, for the endpoint picker."""
    return ok("Endpoints loaded.", api_product_service.endpoint_options(db))


@router.get("/api-products/{api_product_id}")
def get_api_product(api_product_id: int, admin: ManageProducts, db: DbSession):
    return ok("API product loaded.", api_product_service.get_product(db, api_product_id).model_dump())


@router.post("/api-products")
def create_api_product(payload: ApiProductCreate, admin: ManageProducts, db: DbSession):
    product = api_product_service.create_product(db, admin, payload)
    return ok("API product created.", product.model_dump(), code=StatusCode.CREATED)


@router.put("/api-products/{api_product_id}")
def update_api_product(
    api_product_id: int, payload: ApiProductUpdate, admin: ManageProducts, db: DbSession
):
    product = api_product_service.update_product(db, admin, api_product_id, payload)
    return ok("API product updated.", product.model_dump())


@router.post("/api-products/publish")
def publish_api_product(payload: PublishRequest, admin: ManageProducts, db: DbSession):
    product = api_product_service.set_published(db, admin, payload.id, payload.is_published)
    return ok(
        "API product published." if payload.is_published else "API product unpublished.",
        product.model_dump(),
    )


@router.delete("/api-products/{api_product_id}")
def delete_api_product(api_product_id: int, admin: ManageProducts, db: DbSession):
    api_product_service.delete_product(db, admin, api_product_id)
    return ok("API product deleted.")


# ------------------------------------------------------------------- apps
@router.post("/apps/list")
def list_apps(payload: AdminAppListQuery, admin: ManageApps, db: DbSession):
    page = app_service.admin_list(db, payload, admin)
    page.rows = [row.model_dump() for row in page.rows]
    return ok("Apps loaded.", page.as_dict("apps"))


@router.get("/apps/{app_id}")
def get_app(app_id: int, admin: ManageApps, db: DbSession):
    return ok("App loaded.", app_service.admin_get(db, app_id).model_dump())


@router.post("/apps/{app_id}/products/{api_product_id}/approve")
def approve_product(
    app_id: int, api_product_id: int, payload: SubscriptionDecision, admin: ManageApps, db: DbSession
):
    app = app_service.decide_product(
        db, admin, app_id, api_product_id, SubscriptionStatus.APPROVED, payload.remarks
    )
    return ok("Access approved.", app.model_dump())


@router.post("/apps/{app_id}/products/{api_product_id}/reject")
def reject_product(
    app_id: int, api_product_id: int, payload: SubscriptionReject, admin: ManageApps, db: DbSession
):
    app = app_service.decide_product(
        db, admin, app_id, api_product_id, SubscriptionStatus.REJECTED, payload.remarks
    )
    return ok("Request rejected.", app.model_dump())


@router.post("/apps/{app_id}/products/{api_product_id}/revoke")
def revoke_product(
    app_id: int, api_product_id: int, payload: SubscriptionReject, admin: ManageApps, db: DbSession
):
    app = app_service.decide_product(
        db, admin, app_id, api_product_id, SubscriptionStatus.REVOKED, payload.remarks
    )
    return ok("Access revoked.", app.model_dump())


@router.post("/apps/{app_id}/approve")
def approve_app(app_id: int, payload: SubscriptionDecision, admin: ManageApps, db: DbSession):
    """Approve a new app: its open product requests are granted and its first key issued."""
    app = app_service.approve_app(db, admin, app_id, payload.remarks)
    return ok("App approved. Its API key and secret are now available to the participant.", app.model_dump())


@router.post("/apps/{app_id}/reject")
def reject_app(app_id: int, payload: AppRevokeRequest, admin: ManageApps, db: DbSession):
    app = app_service.reject_app(db, admin, app_id, payload.reason)
    return ok("App rejected.", app.model_dump())


@router.post("/apps/{app_id}/revoke")
def revoke_app(app_id: int, payload: AppRevokeRequest, admin: ManageApps, db: DbSession):
    return ok("App revoked.", app_service.revoke_app(db, admin, app_id, payload.reason).model_dump())


@router.post("/apps/{app_id}/restore")
def restore_app(app_id: int, admin: ManageApps, db: DbSession):
    return ok("App restored.", app_service.restore_app(db, admin, app_id).model_dump())


@router.post("/apps/{app_id}/gateway-sync")
def resync_app(app_id: int, admin: ManageApps, db: DbSession):
    app = app_service.resync(db, admin, app_id)
    return ok(f"Gateway sync: {app.gateway_status}.", app.model_dump())
