"""Master data administration: lookups, product categories, countries, geography."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query

from app.core.deps import AdminPrincipal, DbSession, require_permission
from app.core.permissions import Permission
from app.core.responses import ok
from app.schemas.common import ListQuery, ToggleRequest
from app.schemas.masters import (
    AdminAreaCreate,
    AdminAreaUpdate,
    AreaQuery,
    CountryCreate,
    CountryUpdate,
    LookupCreate,
    LookupUpdate,
    ProductCategoryCreateForm,
    ProductCategoryUpdateForm,
)
from app.services import master_service
from app.utils.files import save_upload

router = APIRouter(tags=["Admin / Master Data"])

ManageMasters = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.MASTER_ENTRY))
]
ManageGeography = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.MANAGE_GEOGRAPHY))
]
ManageCountries = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.COUNTRY_MANAGEMENT))
]

ICON_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}


# --------------------------------------------------------------- lookups
@router.get("/lookups/{kind}")
def list_lookup(
    kind: str,
    admin: ManageMasters,
    db: DbSession,
    only_enabled: bool = Query(False),
    country_code: str | None = Query(None),
    parent_id: int | None = Query(None),
    search: str | None = Query(None),
):
    rows = master_service.list_lookup(
        db, kind, only_enabled, country_code, parent_id, search
    )
    return ok("Master data loaded.", [row.model_dump() for row in rows])


@router.post("/lookups/{kind}")
def create_lookup(
    kind: str, payload: LookupCreate, admin: ManageMasters, db: DbSession
):
    row = master_service.create_lookup(db, admin, kind, payload)
    return ok("Entry created successfully.", row.model_dump())


@router.put("/lookups/{kind}")
def update_lookup(
    kind: str, payload: LookupUpdate, admin: ManageMasters, db: DbSession
):
    row = master_service.update_lookup(db, admin, kind, payload)
    return ok("Entry updated successfully.", row.model_dump())


@router.post("/lookups/{kind}/toggle")
def toggle_lookup(
    kind: str, payload: ToggleRequest, admin: ManageMasters, db: DbSession
):
    row = master_service.toggle_lookup(db, admin, kind, payload.id, payload.is_enabled)
    return ok("Entry status updated.", row.model_dump())


@router.delete("/lookups/{kind}/{entry_id}")
def delete_lookup(kind: str, entry_id: int, admin: ManageMasters, db: DbSession):
    master_service.delete_lookup(db, admin, kind, entry_id)
    return ok("Entry deleted successfully.")


# ------------------------------------------------------ product categories
@router.post("/product-categories/list")
def list_product_categories(payload: ListQuery, admin: ManageMasters, db: DbSession):
    page = master_service.list_product_categories(db, payload)
    return ok("Categories loaded.", page.as_dict("categories"))


@router.post("/product-categories")
async def create_product_category(
    admin: ManageMasters,
    db: DbSession,
    payload: Annotated[ProductCategoryCreateForm, Form()],
):
    icon_path = (
        (await save_upload(payload.icon, "categories", ICON_EXTENSIONS)).path
        if payload.icon
        else None
    )
    row = master_service.create_product_category(db, admin, payload, icon_path)
    return ok("Category created successfully.", row.model_dump())


@router.put("/product-categories")
async def update_product_category(
    admin: ManageMasters,
    db: DbSession,
    payload: Annotated[ProductCategoryUpdateForm, Form()],
):
    icon_path = (
        (await save_upload(payload.icon, "categories", ICON_EXTENSIONS)).path
        if payload.icon
        else None
    )
    row = master_service.update_product_category(db, admin, payload, icon_path)
    return ok("Category updated successfully.", row.model_dump())


@router.delete("/product-categories/{category_id}")
def delete_product_category(category_id: int, admin: ManageMasters, db: DbSession):
    master_service.delete_product_category(db, admin, category_id)
    return ok("Category deleted successfully.")


# ------------------------------------------------------------- countries
@router.get("/countries")
def list_countries(admin: ManageCountries, db: DbSession):
    rows = master_service.list_countries(db)
    return ok("Countries loaded.", [row.model_dump() for row in rows])


@router.get("/countries/{country_code}")
def get_country(country_code: str, admin: ManageCountries, db: DbSession):
    return ok(
        "Country loaded.",
        master_service.get_country(db, country_code).model_dump(),
    )


@router.post("/countries")
def create_country(payload: CountryCreate, admin: ManageCountries, db: DbSession):
    country = master_service.create_country(db, admin, payload)
    return ok("Country onboarded successfully.", country.model_dump())


@router.put("/countries/{country_code}")
def update_country(
    country_code: str, payload: CountryUpdate, admin: ManageCountries, db: DbSession
):
    country = master_service.update_country(db, admin, country_code, payload)
    return ok("Country updated successfully.", country.model_dump())


# ------------------------------------------------------------- geography
@router.post("/areas/list")
def list_areas(payload: AreaQuery, admin: ManageGeography, db: DbSession):
    rows = master_service.list_areas(db, payload)
    return ok("Areas loaded.", [row.model_dump() for row in rows])


@router.get("/areas/tree")
def area_tree(
    admin: ManageGeography,
    db: DbSession,
    country_code: str = Query(...),
    max_level: int = Query(2, ge=1, le=4),
):
    nodes = master_service.area_tree(db, country_code, max_level)
    return ok("Area tree loaded.", [node.model_dump() for node in nodes])


@router.post("/areas")
def create_area(payload: AdminAreaCreate, admin: ManageGeography, db: DbSession):
    area = master_service.create_area(db, admin, payload)
    return ok("Area created successfully.", area.model_dump())


@router.put("/areas")
def update_area(payload: AdminAreaUpdate, admin: ManageGeography, db: DbSession):
    area = master_service.update_area(db, admin, payload)
    return ok("Area updated successfully.", area.model_dump())


@router.post("/areas/toggle")
def toggle_area(payload: ToggleRequest, admin: ManageGeography, db: DbSession):
    area = master_service.toggle_area(db, admin, payload.id, payload.is_enabled)
    return ok("Area status updated.", area.model_dump())


@router.post("/areas/{area_id}/api-data")
def toggle_area_api_data(
    area_id: int, admin: ManageGeography, db: DbSession, enabled: bool = Query(...)
):
    """Control whether sandbox APIs return data for this area."""
    area = master_service.toggle_area_api_data(db, admin, area_id, enabled)
    return ok("Area API availability updated.", area.model_dump())
