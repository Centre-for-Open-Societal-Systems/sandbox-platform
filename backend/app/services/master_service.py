"""Lookup tables, product categories and the geography tree."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.deps import AdminPrincipal
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page
from app.models.geo import AdminArea, Country
from app.repositories.master_repository import (
    AdminAreaRepository,
    CountryRepository,
    LookupRepository,
    ProductCategoryRepository,
)
from app.schemas.common import DropdownItem
from app.schemas.masters import (
    AdminAreaCreate,
    AdminAreaOut,
    AdminAreaTreeNode,
    AdminAreaUpdate,
    AreaQuery,
    CountryCreate,
    CountryOut,
    CountryUpdate,
    LookupCreate,
    LookupOut,
    LookupUpdate,
    ProductCategoryCreate,
    ProductCategoryOut,
    ProductCategoryUpdate,
)
from app.services import audit_service
from app.services.audit_service import Action


# ------------------------------------------------------------------ lookups
def list_lookup(
    db: Session,
    kind: str,
    only_enabled: bool = True,
    country_code: str | None = None,
    parent_id: int | None = None,
    search: str | None = None,
) -> list[LookupOut]:
    repo = LookupRepository(db, kind)
    rows = repo.list_rows(only_enabled, country_code, parent_id, search)
    return [LookupOut.model_validate(repo.to_dict(row)) for row in rows]


def lookup_dropdown(
    db: Session,
    kind: str,
    country_code: str | None = None,
    parent_id: int | None = None,
) -> list[DropdownItem]:
    repo = LookupRepository(db, kind)
    rows = repo.list_rows(True, country_code, parent_id)
    return [
        DropdownItem(
            label=getattr(row, repo.spec.name_column),
            value=getattr(row, repo.spec.pk),
        )
        for row in rows
    ]


def create_lookup(
    db: Session, admin: AdminPrincipal, kind: str, payload: LookupCreate
) -> LookupOut:
    repo = LookupRepository(db, kind)
    if repo.name_taken(payload.name, parent_id=payload.parent_id):
        raise ConflictError("An entry with this name already exists.")

    row = repo.create(
        payload.name,
        admin.id,
        sort_order=payload.sort_order,
        country_code=payload.country_code or admin.country_code,
        parent_id=payload.parent_id,
        code=payload.code,
    )
    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_CREATE,
        entity=kind,
        entity_id=getattr(row, repo.spec.pk),
        description=f"Created {kind} '{payload.name}'",
    )
    return LookupOut.model_validate(repo.to_dict(row))


def update_lookup(
    db: Session, admin: AdminPrincipal, kind: str, payload: LookupUpdate
) -> LookupOut:
    repo = LookupRepository(db, kind)
    row = repo.get_or_404(payload.id)
    if payload.name and repo.name_taken(payload.name, payload.id, payload.parent_id):
        raise ConflictError("An entry with this name already exists.")

    repo.update(
        row,
        admin.id,
        name=payload.name,
        sort_order=payload.sort_order,
        country_code=payload.country_code,
        parent_id=payload.parent_id,
        code=payload.code,
    )
    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_UPDATE,
        entity=kind,
        entity_id=payload.id,
        description=f"Updated {kind} entry {payload.id}",
    )
    return LookupOut.model_validate(repo.to_dict(row))


def toggle_lookup(
    db: Session,
    admin: AdminPrincipal,
    kind: str,
    entry_id: int,
    is_enabled: bool | None,
) -> LookupOut:
    repo = LookupRepository(db, kind)
    row = repo.get_or_404(entry_id)
    repo.toggle(row, is_enabled, admin.id)

    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_TOGGLE,
        entity=kind,
        entity_id=entry_id,
        description=f"{'Enabled' if row.is_enabled else 'Disabled'} {kind} entry {entry_id}",
    )
    return LookupOut.model_validate(repo.to_dict(row))


def delete_lookup(db: Session, admin: AdminPrincipal, kind: str, entry_id: int) -> None:
    repo = LookupRepository(db, kind)
    row = repo.get_or_404(entry_id)
    repo.soft_delete(row, admin.id)

    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_DELETE,
        entity=kind,
        entity_id=entry_id,
        description=f"Deleted {kind} entry {entry_id}",
    )


# -------------------------------------------------------- product categories
def list_product_categories(db: Session, query) -> Page:
    page = ProductCategoryRepository(db).paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
        country_code=query.filters.get("country_code"),
    )
    page.rows = [ProductCategoryOut.model_validate(row) for row in page.rows]
    return page


def create_product_category(
    db: Session,
    admin: AdminPrincipal,
    payload: ProductCategoryCreate,
    icon_path: str | None = None,
) -> ProductCategoryOut:
    row = ProductCategoryRepository(db).create(
        **payload.model_dump(exclude={"icon_path", "icon"}),
        icon_path=icon_path or payload.icon_path,
        added_by=admin.id,
        modify_by=admin.id,
    )
    return ProductCategoryOut.model_validate(row)


def update_product_category(
    db: Session,
    admin: AdminPrincipal,
    payload: ProductCategoryUpdate,
    icon_path: str | None = None,
) -> ProductCategoryOut:
    repo = ProductCategoryRepository(db)
    row = repo.get(payload.category_id)
    if row is None:
        raise NotFoundError("Category not found.")

    values = payload.model_dump(
        exclude={"category_id", "icon", "icon_path"}, exclude_unset=True
    )
    # Keep the current icon unless a new one was uploaded or given.
    if icon_path or payload.icon_path:
        values["icon_path"] = icon_path or payload.icon_path
    repo.update(row, **values, modify_by=admin.id)
    return ProductCategoryOut.model_validate(row)


def delete_product_category(
    db: Session, admin: AdminPrincipal, category_id: int
) -> None:
    repo = ProductCategoryRepository(db)
    row = repo.get(category_id)
    if row is None:
        raise NotFoundError("Category not found.")
    repo.soft_delete(row, admin.id)


# ---------------------------------------------------------------- countries
def list_countries(db: Session, only_live: bool = False) -> list[CountryOut]:
    repo = CountryRepository(db)
    countries = repo.live_countries()
    if only_live:
        countries = [country for country in countries if country.is_live]
    return [CountryOut.model_validate(country) for country in countries]


def get_country(db: Session, country_code: str) -> CountryOut:
    return CountryOut.model_validate(_require_country(db, country_code))


def create_country(
    db: Session, admin: AdminPrincipal, payload: CountryCreate
) -> CountryOut:
    repo = CountryRepository(db)
    if repo.get_by_code(payload.country_code):
        raise ConflictError("This country is already registered on the network.")

    country = repo.create(
        **payload.model_dump(exclude={"country_code"}),
        country_code=payload.country_code.upper(),
        added_by=admin.id,
        modify_by=admin.id,
    )
    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_CREATE,
        entity="country",
        entity_id=country.country_id,
        description=f"Onboarded country {country.country_name}",
    )
    return CountryOut.model_validate(country)


def update_country(
    db: Session, admin: AdminPrincipal, country_code: str, payload: CountryUpdate
) -> CountryOut:
    repo = CountryRepository(db)
    country = _require_country(db, country_code)
    repo.update(
        country,
        **payload.model_dump(exclude={"country_code"}, exclude_none=True),
        modify_by=admin.id,
    )
    return CountryOut.model_validate(country)


# --------------------------------------------------------------- geography
def list_areas(db: Session, query: AreaQuery) -> list[AdminAreaOut]:
    repo = AdminAreaRepository(db)
    country_code = (query.country_code or "").upper()

    if query.parent_code and country_code:
        parent = repo.get_by_code(country_code, query.parent_code)
        if parent is None:
            raise NotFoundError("Parent area not found.")
        areas = repo.children_of(parent.area_id, country_code)
    elif query.parent_id:
        areas = repo.children_of(query.parent_id, country_code)
    elif query.level and country_code:
        areas = repo.by_level(country_code, query.level, query.only_enabled)
    else:
        areas = repo.children_of(None, country_code, query.level)

    if query.search:
        needle = query.search.strip().lower()
        areas = [area for area in areas if needle in area.area_name.lower()]

    return _to_area_outs(db, areas)


def area_dropdown(
    db: Session, country_code: str, level: int, parent_id: int | None = None
) -> list[DropdownItem]:
    repo = AdminAreaRepository(db)
    areas = (
        repo.children_of(parent_id, country_code, level)
        if parent_id
        else repo.by_level(country_code, level)
    )
    return [DropdownItem(label=area.area_name, value=area.area_code) for area in areas]


def area_tree(
    db: Session, country_code: str, max_level: int = 2
) -> list[AdminAreaTreeNode]:
    """Country tree down to ``max_level``, built in one pass over the rows."""
    repo = AdminAreaRepository(db)
    country = _require_country(db, country_code)
    labels = country.level_labels or {}

    rows = [
        area
        for level in range(1, min(max_level, country.level_depth) + 1)
        for area in repo.by_level(country_code, level)
    ]

    nodes: dict[int, AdminAreaTreeNode] = {}
    for area in rows:
        node = AdminAreaTreeNode.model_validate(area)
        node.level_label = labels.get(str(area.level))
        nodes[area.area_id] = node

    roots: list[AdminAreaTreeNode] = []
    for area in rows:
        node = nodes[area.area_id]
        parent = nodes.get(area.parent_id) if area.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


def create_area(
    db: Session, admin: AdminPrincipal, payload: AdminAreaCreate
) -> AdminAreaOut:
    repo = AdminAreaRepository(db)
    country_code = payload.country_code.upper()
    _require_country(db, country_code)

    if repo.get_by_code(country_code, payload.area_code):
        raise ConflictError("An area with this code already exists for the country.")
    _assert_parent_level(repo, payload.parent_id, payload.level)

    area = repo.create(
        **payload.model_dump(exclude={"country_code"}),
        country_code=country_code,
        added_by=admin.id,
        modify_by=admin.id,
    )
    area.path = repo.compute_path(payload.parent_id, area.area_id)
    db.commit()

    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_CREATE,
        entity="admin_area",
        entity_id=area.area_id,
        description=f"Created area {area.area_name}",
        country_code=country_code,
    )
    return _to_area_outs(db, [area])[0]


def update_area(
    db: Session, admin: AdminPrincipal, payload: AdminAreaUpdate
) -> AdminAreaOut:
    repo = AdminAreaRepository(db)
    area = repo.get(payload.area_id)
    if area is None:
        raise NotFoundError("Area not found.")
    if payload.level:
        _assert_parent_level(repo, payload.parent_id or area.parent_id, payload.level)

    repo.update(
        area,
        **payload.model_dump(exclude={"area_id", "country_code"}, exclude_none=True),
        modify_by=admin.id,
    )
    if payload.parent_id is not None:
        area.path = repo.compute_path(payload.parent_id, area.area_id)
        db.commit()

    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_UPDATE,
        entity="admin_area",
        entity_id=area.area_id,
        description=f"Updated area {area.area_name}",
        country_code=area.country_code,
    )
    return _to_area_outs(db, [area])[0]


def toggle_area(
    db: Session, admin: AdminPrincipal, area_id: int, is_enabled: bool | None
) -> AdminAreaOut:
    repo = AdminAreaRepository(db)
    area = repo.get(area_id)
    if area is None:
        raise NotFoundError("Area not found.")

    repo.toggle(area, is_enabled, admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.MASTER_TOGGLE,
        entity="admin_area",
        entity_id=area_id,
        description=f"{'Enabled' if area.is_enabled else 'Disabled'} area {area.area_name}",
        country_code=area.country_code,
    )
    return _to_area_outs(db, [area])[0]


def toggle_area_api_data(
    db: Session, admin: AdminPrincipal, area_id: int, enabled: bool
) -> AdminAreaOut:
    """Control whether sandbox APIs serve data for an area."""
    repo = AdminAreaRepository(db)
    area = repo.get(area_id)
    if area is None:
        raise NotFoundError("Area not found.")

    repo.update(area, is_api_data_enabled=enabled, modify_by=admin.id)
    return _to_area_outs(db, [area])[0]


# ------------------------------------------------------------------ helpers
def _require_country(db: Session, country_code: str) -> Country:
    country = CountryRepository(db).get_by_code(country_code)
    if country is None:
        raise NotFoundError("Country is not registered on the network.")
    return country


def _assert_parent_level(
    repo: AdminAreaRepository, parent_id: int | None, level: int
) -> None:
    """A level-N area must hang off a level-(N-1) parent."""
    if level == 1:
        if parent_id:
            raise ValidationError("A top-level area cannot have a parent.")
        return

    if not parent_id:
        raise ValidationError("A parent area is required below the top level.")
    parent = repo.get(parent_id)
    if parent is None:
        raise ValidationError("Parent area not found.")
    if parent.level != level - 1:
        raise ValidationError("The parent area is at the wrong level in the hierarchy.")


def _to_area_outs(db: Session, areas: list[AdminArea]) -> list[AdminAreaOut]:
    if not areas:
        return []

    repo = AdminAreaRepository(db)
    child_counts = repo.child_counts([area.area_id for area in areas])
    countries = CountryRepository(db)
    label_cache: dict[str, dict] = {}

    results = []
    for area in areas:
        if area.country_code not in label_cache:
            country = countries.get_by_code(area.country_code)
            label_cache[area.country_code] = (
                (country.level_labels or {}) if country else {}
            )
        out = AdminAreaOut.model_validate(area)
        out.level_label = label_cache[area.country_code].get(str(area.level))
        out.child_count = child_counts.get(area.area_id, 0)
        results.append(out)
    return results
