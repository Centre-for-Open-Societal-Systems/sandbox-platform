"""API catalogue administration and the public catalogue view."""

from __future__ import annotations

import hashlib
import json
import threading

from sqlalchemy.orm import Session

from app.core.deps import AdminPrincipal
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page
from app.models.catalog import Endpoint, Product
from app.repositories.catalog_repository import (
    EndpointRepository,
    EndpointSchemaRepository,
    MapperRepository,
    ProductRepository,
)
from app.schemas.catalog import (
    CatalogMenuEndpoint,
    CatalogMenuProduct,
    EndpointCreate,
    EndpointDetailOut,
    EndpointListQuery,
    EndpointOut,
    EndpointSchemaCreate,
    EndpointSchemaOut,
    EndpointSchemaUpdate,
    EndpointUpdate,
    MapperCreate,
    MapperOut,
    MapperUpdate,
    ProductCreate,
    ProductDetailOut,
    ProductListQuery,
    ProductOut,
    ProductUpdate,
)
from app.services import audit_service, sandbox_service
from app.services.audit_service import Action
from app.utils import schema_tools
from app.utils.files import public_url


# ---------------------------------------------------------------- products
def list_products(db: Session, query: ProductListQuery) -> Page:
    repo = ProductRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
        category_id=query.category_id,
        country_code=query.country_code,
        is_published=query.is_published,
    )
    page.rows = _decorate_products(repo, page.rows)
    return page


def list_published_products(
    db: Session, country_code: str | None = None
) -> list[ProductOut]:
    repo = ProductRepository(db)
    products = list(db.execute(repo.published_stmt(country_code)).scalars().all())
    return _decorate_products(repo, products)


#: country code -> (catalogue version, menu payload, ETag). One entry per
#: member country; rebuilt only when the catalogue fingerprint changes.
_menu_cache: dict[str | None, tuple[str, list[dict], str]] = {}
_menu_lock = threading.Lock()


def catalog_menu(db: Session, country_code: str | None = None) -> tuple[list[dict], str]:
    """Every published product with its published end-points, for the API menu.

    One call instead of one per product. Built with two queries, cached per
    country and keyed on a catalogue fingerprint (one cheap query), so a change
    made by any worker or script is picked up on the next request. Returns the
    payload and its ETag.
    """
    repo = ProductRepository(db)
    version = repo.catalog_version()
    cached = _menu_cache.get(country_code)
    if cached and cached[0] == version:
        return cached[1], cached[2]

    products = list(db.execute(repo.published_stmt(country_code)).scalars().all())
    category_names = repo.category_names([p.category_id for p in products])
    by_product: dict[int, list[CatalogMenuEndpoint]] = {}
    for row in repo.published_endpoint_rows(
        [p.product_id for p in products]
    ):
        by_product.setdefault(row.product_id, []).append(
            CatalogMenuEndpoint(
                endpoint_id=row.endpoint_id,
                display_name=row.display_name,
                endpoint_url=row.endpoint_url,
                method=row.method,
                api_type=row.api_type,
            )
        )
    menu = [
        CatalogMenuProduct(
            product_id=p.product_id,
            product_name=p.product_name,
            display_name=p.display_name,
            category_name=category_names.get(p.category_id) if p.category_id else None,
            endpoints=by_product.get(p.product_id, []),
        ).model_dump()
        for p in products
    ]
    etag = '"' + hashlib.sha256(
        json.dumps(menu, sort_keys=True, default=str).encode()
    ).hexdigest()[:32] + '"'
    with _menu_lock:
        _menu_cache[country_code] = (version, menu, etag)
    return menu, etag


def get_product(
    db: Session, product_id: int, published_only: bool = False
) -> ProductDetailOut:
    product = _require_product(db, product_id)
    if published_only and not product.is_published:
        raise NotFoundError("Product not found.")

    endpoints = EndpointRepository(db).for_product(product_id, published_only)
    detail = ProductDetailOut.model_validate(product)
    detail.product_icon = public_url(product.product_icon)
    detail.flow_chart = public_url(product.flow_chart)
    detail.product_documentation_pdf = public_url(product.product_documentation_pdf)
    detail.endpoint_count = len(endpoints)
    detail.endpoints = [EndpointOut.model_validate(endpoint) for endpoint in endpoints]
    if published_only:
        # The stored OpenAPI document is an admin artefact (often hundreds of KB
        # of shared components); portal pages render from the end-points.
        detail.open_spec_json = None
    return detail


def create_product(
    db: Session, admin: AdminPrincipal, payload: ProductCreate
) -> ProductOut:
    repo = ProductRepository(db)
    if repo.name_taken(payload.product_name):
        raise ConflictError("A product with this name already exists.")

    values = payload.model_dump()
    # A product with no country of its own is offered network-wide, so fall
    # back to the creating administrator's country rather than to NULL.
    values["country_code"] = payload.country_code or admin.country_code

    product = repo.create(**values, added_by=admin.id, modify_by=admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.PRODUCT_CREATE,
        entity="product",
        entity_id=product.product_id,
        description=f"Created product {product.product_name}",
    )
    return _decorate_products(repo, [product])[0]


def update_product(
    db: Session, admin: AdminPrincipal, payload: ProductUpdate
) -> ProductOut:
    repo = ProductRepository(db)
    product = _require_product(db, payload.product_id)
    if payload.product_name and repo.name_taken(
        payload.product_name, product.product_id
    ):
        raise ConflictError("A product with this name already exists.")

    repo.update(
        product,
        **payload.model_dump(exclude={"product_id"}, exclude_unset=True),
        modify_by=admin.id,
    )
    audit_service.record_admin(
        db,
        admin,
        Action.PRODUCT_UPDATE,
        entity="product",
        entity_id=product.product_id,
        description=f"Updated product {product.product_name}",
    )
    return _decorate_products(repo, [product])[0]


def set_product_assets(
    db: Session,
    admin: AdminPrincipal,
    product_id: int,
    icon_path: str | None = None,
    flow_chart_path: str | None = None,
    documentation_path: str | None = None,
) -> ProductOut:
    repo = ProductRepository(db)
    product = _require_product(db, product_id)
    repo.update(
        product,
        product_icon=icon_path,
        flow_chart=flow_chart_path,
        product_documentation_pdf=documentation_path,
        modify_by=admin.id,
    )
    return _decorate_products(repo, [product])[0]


def publish_product(
    db: Session, admin: AdminPrincipal, product_id: int, is_published: bool
) -> ProductOut:
    repo = ProductRepository(db)
    product = _require_product(db, product_id)

    if is_published and not EndpointRepository(db).for_product(product_id):
        raise ValidationError(
            "Add at least one endpoint before publishing this product."
        )

    repo.update(product, is_published=is_published, modify_by=admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.PRODUCT_PUBLISH,
        entity="product",
        entity_id=product_id,
        description=f"{'Published' if is_published else 'Unpublished'} {product.product_name}",
    )
    return _decorate_products(repo, [product])[0]


def delete_product(db: Session, admin: AdminPrincipal, product_id: int) -> None:
    repo = ProductRepository(db)
    product = _require_product(db, product_id)
    if product.is_published:
        raise ConflictError("Unpublish this product before deleting it.")

    repo.soft_delete(product, admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.PRODUCT_DELETE,
        entity="product",
        entity_id=product_id,
        description=f"Deleted product {product.product_name}",
    )


def import_specification(
    db: Session,
    admin: AdminPrincipal,
    product_id: int,
    spec_text: str,
    replace_existing: bool,
) -> dict:
    """Create or refresh endpoints from an OpenAPI document."""
    product = _require_product(db, product_id)
    spec = schema_tools.parse_spec(spec_text)
    operations = schema_tools.endpoints_from_spec(spec)
    if not operations:
        raise ValidationError("The specification does not define any operations.")

    endpoints = EndpointRepository(db)
    schemas = EndpointSchemaRepository(db)

    if replace_existing:
        for existing in endpoints.for_product(product_id):
            endpoints.soft_delete(existing, admin.id)

    created = 0
    updated = 0
    for operation in operations:
        responses = operation.pop("responses", [])
        existing = endpoints.find_by_route(
            product_id, operation["method"], operation["endpoint_url"]
        )
        if existing is None:
            endpoint = endpoints.create(
                product_id=product_id,
                added_by=admin.id,
                modify_by=admin.id,
                **operation,
            )
            created += 1
        else:
            endpoint = endpoints.update(existing, modify_by=admin.id, **operation)
            updated += 1
        _sync_response_schemas(schemas, endpoint, responses, admin.id)

    product.open_spec = spec_text
    product.open_spec_json = spec
    product.api_doc_version = str(spec.get("info", {}).get("version") or "")
    product.modify_by = admin.id
    db.commit()

    audit_service.record_admin(
        db,
        admin,
        Action.SPEC_IMPORT,
        entity="product",
        entity_id=product_id,
        description=f"Imported specification: {created} created, {updated} updated",
    )
    return {"created": created, "updated": updated, "total": len(operations)}


# --------------------------------------------------------------- endpoints
def list_endpoints(db: Session, query: EndpointListQuery) -> Page:
    repo = EndpointRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
        product_id=query.product_id,
        api_type=str(query.api_type) if query.api_type else None,
        country_code=query.country_code,
        is_published=query.is_published,
    )
    product_names = repo.product_names([endpoint.product_id for endpoint in page.rows])
    page.rows = [_to_endpoint_out(endpoint, product_names) for endpoint in page.rows]
    return page


def get_endpoint(
    db: Session, endpoint_id: int, published_only: bool = False
) -> EndpointDetailOut:
    endpoint = _require_endpoint(db, endpoint_id)
    if published_only and not endpoint.is_published:
        raise NotFoundError("Endpoint not found.")

    detail = EndpointDetailOut.model_validate(endpoint)
    detail.product_name = (
        EndpointRepository(db)
        .product_names([endpoint.product_id])
        .get(endpoint.product_id)
    )
    detail.schemas = [
        EndpointSchemaOut.model_validate(row)
        for row in EndpointSchemaRepository(db).for_endpoint(endpoint_id)
    ]
    if not published_only:
        detail.resolved_upstreams = sandbox_service.upstream_urls(endpoint)
    return detail


def create_endpoint(
    db: Session, admin: AdminPrincipal, payload: EndpointCreate
) -> EndpointOut:
    _require_product(db, payload.product_id)
    repo = EndpointRepository(db)

    if repo.find_by_route(
        payload.product_id, str(payload.method), payload.endpoint_url
    ):
        raise ConflictError("This method and path already exist on the product.")

    values = payload.model_dump()
    values["method"] = str(payload.method)
    values["api_type"] = str(payload.api_type)

    endpoint = repo.create(**values, added_by=admin.id, modify_by=admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.ENDPOINT_CREATE,
        entity="endpoint",
        entity_id=endpoint.endpoint_id,
        description=f"Created endpoint {endpoint.method} {endpoint.endpoint_url}",
    )
    return _to_endpoint_out(endpoint, repo.product_names([endpoint.product_id]))


def update_endpoint(
    db: Session, admin: AdminPrincipal, payload: EndpointUpdate
) -> EndpointOut:
    repo = EndpointRepository(db)
    endpoint = _require_endpoint(db, payload.endpoint_id)

    values = payload.model_dump(exclude={"endpoint_id"}, exclude_unset=True)
    if "method" in values:
        values["method"] = str(payload.method)
    if "api_type" in values:
        values["api_type"] = str(payload.api_type)

    repo.update(endpoint, **values, modify_by=admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.ENDPOINT_UPDATE,
        entity="endpoint",
        entity_id=endpoint.endpoint_id,
        description=f"Updated endpoint {endpoint.method} {endpoint.endpoint_url}",
    )
    return _to_endpoint_out(endpoint, repo.product_names([endpoint.product_id]))


def publish_endpoint(
    db: Session, admin: AdminPrincipal, endpoint_id: int, is_published: bool
) -> EndpointOut:
    repo = EndpointRepository(db)
    endpoint = _require_endpoint(db, endpoint_id)
    repo.update(endpoint, is_published=is_published, modify_by=admin.id)

    audit_service.record_admin(
        db,
        admin,
        Action.ENDPOINT_PUBLISH,
        entity="endpoint",
        entity_id=endpoint_id,
        description=f"{'Published' if is_published else 'Unpublished'} {endpoint.endpoint_url}",
    )
    return _to_endpoint_out(endpoint, repo.product_names([endpoint.product_id]))


def delete_endpoint(db: Session, admin: AdminPrincipal, endpoint_id: int) -> None:
    repo = EndpointRepository(db)
    endpoint = _require_endpoint(db, endpoint_id)
    repo.soft_delete(endpoint, admin.id)

    audit_service.record_admin(
        db,
        admin,
        Action.ENDPOINT_DELETE,
        entity="endpoint",
        entity_id=endpoint_id,
        description=f"Deleted endpoint {endpoint.endpoint_url}",
    )


# --------------------------------------------------------- endpoint schemas
def list_schemas(db: Session, endpoint_id: int) -> list[EndpointSchemaOut]:
    rows = EndpointSchemaRepository(db).for_endpoint(endpoint_id)
    return [EndpointSchemaOut.model_validate(row) for row in rows]


def create_schema(
    db: Session, admin: AdminPrincipal, payload: EndpointSchemaCreate
) -> EndpointSchemaOut:
    endpoint = _require_endpoint(db, payload.endpoint_id)
    repo = EndpointSchemaRepository(db)
    if repo.status_taken(payload.endpoint_id, payload.status_code):
        raise ConflictError(
            f"A schema for status {payload.status_code} already exists."
        )

    row = repo.create(
        **payload.model_dump(),
        product_id=endpoint.product_id,
        added_by=admin.id,
        modify_by=admin.id,
    )
    audit_service.record_admin(
        db,
        admin,
        Action.SCHEMA_UPSERT,
        entity="endpoint_schema",
        entity_id=row.schema_id,
        description=f"Added {payload.status_code} schema to endpoint {endpoint.endpoint_id}",
    )
    return EndpointSchemaOut.model_validate(row)


def update_schema(
    db: Session, admin: AdminPrincipal, payload: EndpointSchemaUpdate
) -> EndpointSchemaOut:
    repo = EndpointSchemaRepository(db)
    row = repo.get(payload.schema_id)
    if row is None:
        raise NotFoundError("Schema not found.")
    # Only the fields the client actually sent are written, so a partial
    # update cannot erase the request/response samples it left out.
    changes = payload.model_dump(
        exclude={"schema_id", "endpoint_id"}, exclude_unset=True
    )
    if "status_code" in changes and repo.status_taken(
        row.endpoint_id, changes["status_code"], row.schema_id
    ):
        raise ConflictError(
            f"A schema for status {changes['status_code']} already exists."
        )

    repo.set_fields(row, **changes, modify_by=admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.SCHEMA_UPSERT,
        entity="endpoint_schema",
        entity_id=row.schema_id,
        description=f"Updated {row.status_code} schema",
    )
    return EndpointSchemaOut.model_validate(row)


def delete_schema(db: Session, admin: AdminPrincipal, schema_id: int) -> None:
    repo = EndpointSchemaRepository(db)
    row = repo.get(schema_id)
    if row is None:
        raise NotFoundError("Schema not found.")
    repo.soft_delete(row, admin.id)


def generate_schema(sample) -> dict:
    return schema_tools.infer_schema(sample)


# ------------------------------------------------------------------ mappers
def list_mappers(db: Session, query) -> Page:
    page = MapperRepository(db).paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
    )
    page.rows = [MapperOut.model_validate(row) for row in page.rows]
    return page


def create_mapper(
    db: Session, admin: AdminPrincipal, payload: MapperCreate
) -> MapperOut:
    repo = MapperRepository(db)
    if repo.name_taken(payload.usecase_name):
        raise ConflictError("A mapper with this use case name already exists.")

    row = repo.create(**payload.model_dump(), added_by=admin.id, modify_by=admin.id)
    return MapperOut.model_validate(row)


def update_mapper(
    db: Session, admin: AdminPrincipal, payload: MapperUpdate
) -> MapperOut:
    repo = MapperRepository(db)
    row = repo.get(payload.mapper_id)
    if row is None:
        raise NotFoundError("Mapper not found.")
    if payload.usecase_name and repo.name_taken(payload.usecase_name, row.mapper_id):
        raise ConflictError("A mapper with this use case name already exists.")

    repo.update(row, **payload.model_dump(exclude={"mapper_id"}), modify_by=admin.id)
    return MapperOut.model_validate(row)


def delete_mapper(db: Session, admin: AdminPrincipal, mapper_id: int) -> None:
    repo = MapperRepository(db)
    row = repo.get(mapper_id)
    if row is None:
        raise NotFoundError("Mapper not found.")
    if repo.in_use(mapper_id):
        raise ConflictError(
            "This mapper is attached to endpoints and cannot be deleted."
        )
    repo.soft_delete(row, admin.id)


def mapper_dropdown(db: Session) -> list[dict]:
    return [
        {"label": row.usecase_name, "value": row.mapper_id}
        for row in MapperRepository(db).list_all(
            only_enabled=True, order_by="usecase_name"
        )
    ]


# ------------------------------------------------------------------ helpers
def _require_product(db: Session, product_id: int) -> Product:
    product = ProductRepository(db).get(product_id)
    if product is None:
        raise NotFoundError("Product not found.")
    return product


def _require_endpoint(db: Session, endpoint_id: int) -> Endpoint:
    endpoint = EndpointRepository(db).get(endpoint_id)
    if endpoint is None:
        raise NotFoundError("Endpoint not found.")
    return endpoint


def _decorate_products(
    repo: ProductRepository, products: list[Product]
) -> list[ProductOut]:
    """Attach endpoint counts, category names and resolved asset URLs."""
    product_ids = [product.product_id for product in products]
    endpoint_counts = repo.endpoint_counts(product_ids)
    category_names = repo.category_names([product.category_id for product in products])

    results = []
    for product in products:
        out = ProductOut.model_validate(product)
        out.endpoint_count = endpoint_counts.get(product.product_id, 0)
        out.category_name = (
            category_names.get(product.category_id) if product.category_id else None
        )
        out.product_icon = public_url(product.product_icon)
        out.flow_chart = public_url(product.flow_chart)
        out.product_documentation_pdf = public_url(product.product_documentation_pdf)
        results.append(out)
    return results


def _to_endpoint_out(endpoint: Endpoint, product_names: dict[int, str]) -> EndpointOut:
    out = EndpointOut.model_validate(endpoint)
    out.product_name = product_names.get(endpoint.product_id)
    return out


def _sync_response_schemas(
    repo: EndpointSchemaRepository,
    endpoint: Endpoint,
    responses: list[dict],
    admin_id: int,
) -> None:
    for response in responses:
        status_code = response.get("status_code") or "200"
        existing = repo.get_for_status(endpoint.endpoint_id, status_code)
        values = {
            "res_schema": response.get("res_schema"),
            "res_json": response.get("res_json"),
            "req_schema": endpoint.request_schema,
            "req_json": endpoint.request_sample,
            "path_params": endpoint.path_params,
        }
        if existing is None:
            repo.create(
                endpoint_id=endpoint.endpoint_id,
                product_id=endpoint.product_id,
                status_code=status_code,
                added_by=admin_id,
                modify_by=admin_id,
                **values,
            )
        else:
            repo.set_fields(existing, modify_by=admin_id, **values)
