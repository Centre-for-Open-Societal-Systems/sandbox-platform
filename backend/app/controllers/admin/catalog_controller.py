"""API catalogue administration: products, endpoints, schemas and mappers."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.deps import AdminPrincipal, DbSession, require_permission
from app.core.exceptions import ValidationError
from app.core.permissions import Permission
from app.core.responses import ok
from app.schemas.catalog import (
    EndpointCreate,
    EndpointListQuery,
    EndpointSchemaCreate,
    EndpointSchemaUpdate,
    EndpointUpdate,
    GenerateSchemaRequest,
    ImportSpecRequest,
    MapperCreate,
    MapperUpdate,
    ProductCreate,
    ProductListQuery,
    ProductUpdate,
    PublishRequest,
)
from app.schemas.common import ListQuery
from app.services import catalog_service
from app.utils.files import extension_of, save_upload

router = APIRouter(tags=["Admin / Catalogue"])

ManageCatalog = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.API_CATALOGUE))
]

SPEC_EXTENSIONS = {"json", "yaml", "yml"}
IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
DOCUMENT_EXTENSIONS = {"pdf"}


# -------------------------------------------------------------- products
@router.post("/products/list")
def list_products(payload: ProductListQuery, admin: ManageCatalog, db: DbSession):
    return ok(
        "Products loaded.",
        catalog_service.list_products(db, payload).as_dict("products"),
    )


@router.get("/products/{product_id}")
def get_product(product_id: int, admin: ManageCatalog, db: DbSession):
    return ok(
        "Product loaded.",
        catalog_service.get_product(db, product_id).model_dump(),
    )


@router.post("/products")
def create_product(payload: ProductCreate, admin: ManageCatalog, db: DbSession):
    product = catalog_service.create_product(db, admin, payload)
    return ok("Product created successfully.", product.model_dump())


@router.put("/products")
def update_product(payload: ProductUpdate, admin: ManageCatalog, db: DbSession):
    product = catalog_service.update_product(db, admin, payload)
    return ok("Product updated successfully.", product.model_dump())


@router.post("/products/publish")
def publish_product(payload: PublishRequest, admin: ManageCatalog, db: DbSession):
    product = catalog_service.publish_product(
        db, admin, payload.id, payload.is_published
    )
    return ok("Product publication updated.", product.model_dump())


@router.delete("/products/{product_id}")
def delete_product(product_id: int, admin: ManageCatalog, db: DbSession):
    catalog_service.delete_product(db, admin, product_id)
    return ok("Product deleted successfully.")


@router.post("/products/{product_id}/assets")
async def upload_product_assets(
    product_id: int,
    admin: ManageCatalog,
    db: DbSession,
    icon: UploadFile | None = File(None),
    flow_chart: UploadFile | None = File(None),
    documentation: UploadFile | None = File(None),
):
    icon_path = (
        (await save_upload(icon, "products/icons", IMAGE_EXTENSIONS)).path
        if icon
        else None
    )
    flow_path = (
        (await save_upload(flow_chart, "products/flowcharts", IMAGE_EXTENSIONS)).path
        if flow_chart
        else None
    )
    doc_path = (
        (await save_upload(documentation, "products/docs", DOCUMENT_EXTENSIONS)).path
        if documentation
        else None
    )

    product = catalog_service.set_product_assets(
        db, admin, product_id, icon_path, flow_path, doc_path
    )
    return ok("Product assets updated.", product.model_dump())


@router.post("/products/import-spec")
def import_spec(payload: ImportSpecRequest, admin: ManageCatalog, db: DbSession):
    if not payload.spec_text:
        return ok("Nothing to import.", {"created": 0, "updated": 0, "total": 0})

    result = catalog_service.import_specification(
        db, admin, payload.product_id, payload.spec_text, payload.replace_existing
    )
    return ok("Specification imported successfully.", result)


@router.post("/products/import-spec/upload")
async def import_spec_file(
    admin: ManageCatalog,
    db: DbSession,
    product_id: int = Form(...),
    replace_existing: bool = Form(False),
    spec_file: UploadFile = File(...),
):
    if extension_of(spec_file.filename or "") not in SPEC_EXTENSIONS:
        raise ValidationError("Upload a JSON or YAML specification file.")

    spec_text = (await spec_file.read()).decode("utf-8")
    result = catalog_service.import_specification(
        db, admin, product_id, spec_text, replace_existing
    )
    return ok("Specification imported successfully.", result)


# ------------------------------------------------------------- endpoints
@router.post("/endpoints/list")
def list_endpoints(payload: EndpointListQuery, admin: ManageCatalog, db: DbSession):
    return ok(
        "Endpoints loaded.",
        catalog_service.list_endpoints(db, payload).as_dict("endpoints"),
    )


@router.get("/endpoints/{endpoint_id}")
def get_endpoint(endpoint_id: int, admin: ManageCatalog, db: DbSession):
    endpoint = catalog_service.get_endpoint(db, endpoint_id)
    return ok("Endpoint loaded.", endpoint.model_dump())


@router.post("/endpoints")
def create_endpoint(payload: EndpointCreate, admin: ManageCatalog, db: DbSession):
    endpoint = catalog_service.create_endpoint(db, admin, payload)
    return ok("Endpoint created successfully.", endpoint.model_dump())


@router.put("/endpoints")
def update_endpoint(payload: EndpointUpdate, admin: ManageCatalog, db: DbSession):
    endpoint = catalog_service.update_endpoint(db, admin, payload)
    return ok("Endpoint updated successfully.", endpoint.model_dump())


@router.post("/endpoints/publish")
def publish_endpoint(payload: PublishRequest, admin: ManageCatalog, db: DbSession):
    endpoint = catalog_service.publish_endpoint(
        db, admin, payload.id, payload.is_published
    )
    return ok("Endpoint publication updated.", endpoint.model_dump())


@router.delete("/endpoints/{endpoint_id}")
def delete_endpoint(endpoint_id: int, admin: ManageCatalog, db: DbSession):
    catalog_service.delete_endpoint(db, admin, endpoint_id)
    return ok("Endpoint deleted successfully.")


# ------------------------------------------------------ endpoint schemas
@router.get("/endpoints/{endpoint_id}/schemas")
def list_schemas(endpoint_id: int, admin: ManageCatalog, db: DbSession):
    schemas = catalog_service.list_schemas(db, endpoint_id)
    return ok("Schemas loaded.", [schema.model_dump() for schema in schemas])


@router.post("/schemas")
def create_schema(payload: EndpointSchemaCreate, admin: ManageCatalog, db: DbSession):
    schema = catalog_service.create_schema(db, admin, payload)
    return ok("Schema created successfully.", schema.model_dump())


@router.put("/schemas")
def update_schema(payload: EndpointSchemaUpdate, admin: ManageCatalog, db: DbSession):
    schema = catalog_service.update_schema(db, admin, payload)
    return ok("Schema updated successfully.", schema.model_dump())


@router.delete("/schemas/{schema_id}")
def delete_schema(schema_id: int, admin: ManageCatalog, db: DbSession):
    catalog_service.delete_schema(db, admin, schema_id)
    return ok("Schema deleted successfully.")


@router.post("/schemas/generate")
def generate_schema(payload: GenerateSchemaRequest, admin: ManageCatalog):
    return ok("Schema generated.", catalog_service.generate_schema(payload.sample))


# --------------------------------------------------------------- mappers
@router.post("/mappers/list")
def list_mappers(payload: ListQuery, admin: ManageCatalog, db: DbSession):
    return ok(
        "Mappers loaded.", catalog_service.list_mappers(db, payload).as_dict("mappers")
    )


@router.get("/mappers/dropdown")
def mapper_dropdown(admin: ManageCatalog, db: DbSession):
    return ok("Mappers loaded.", catalog_service.mapper_dropdown(db))


@router.post("/mappers")
def create_mapper(payload: MapperCreate, admin: ManageCatalog, db: DbSession):
    mapper = catalog_service.create_mapper(db, admin, payload)
    return ok("Mapper created successfully.", mapper.model_dump())


@router.put("/mappers")
def update_mapper(payload: MapperUpdate, admin: ManageCatalog, db: DbSession):
    mapper = catalog_service.update_mapper(db, admin, payload)
    return ok("Mapper updated successfully.", mapper.model_dump())


@router.delete("/mappers/{mapper_id}")
def delete_mapper(mapper_id: int, admin: ManageCatalog, db: DbSession):
    catalog_service.delete_mapper(db, admin, mapper_id)
    return ok("Mapper deleted successfully.")
