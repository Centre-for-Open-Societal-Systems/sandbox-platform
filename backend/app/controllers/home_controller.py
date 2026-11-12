"""Public endpoints - no authentication required."""

from __future__ import annotations

from fastapi import APIRouter, Header, Query
from fastapi.responses import Response

from app.config.settings import settings
from app.core.deps import CountryCode, DbSession, Locale
from app.core.responses import ok
from app.services import (
    catalog_export_service,
    catalog_service,
    content_service,
    file_access_service,
    master_service,
    partner_portal_service,
)
from app.utils.files import extension_of, normalise_upload_path, read_file

router = APIRouter(tags=["Public"])


@router.get("/home")
def home(db: DbSession, locale: Locale, country: CountryCode):
    return ok(
        "Home content loaded.",
        content_service.public_home(db, locale, country).model_dump(),
    )


@router.get("/faqs")
def faqs(db: DbSession, locale: Locale, country: CountryCode):
    groups = content_service.public_faqs(db, locale, country)
    return ok("FAQs loaded.", [group.model_dump() for group in groups])


@router.get("/terms")
def terms(db: DbSession, locale: Locale, country: CountryCode):
    sections = content_service.public_terms(db, locale, country)
    return ok("Terms loaded.", [section.model_dump() for section in sections])


@router.get("/countries")
def countries(db: DbSession, only_live: bool = Query(False)):
    rows = master_service.list_countries(db, only_live)
    return ok("Countries loaded.", [row.model_dump() for row in rows])


@router.get("/catalog/products")
def catalog_products(db: DbSession, country: CountryCode):
    products = catalog_service.list_published_products(db, country)
    return ok("Catalogue loaded.", [product.model_dump() for product in products])


@router.get("/catalog/products/{product_id}")
def catalog_product(product_id: int, db: DbSession):
    return ok(
        "Product loaded.",
        catalog_service.get_product(db, product_id, published_only=True).model_dump(),
    )


@router.get("/catalog/products/{product_id}/openapi")
def catalog_product_openapi(product_id: int, db: DbSession):
    """Public: OpenAPI 3.0 document of a published product (sandbox/UAT gateway, no keys)."""
    return ok("OpenAPI document generated.", catalog_export_service.openapi_document(db, product_id))


@router.get("/masters/{kind}")
def master_list(
    kind: str, db: DbSession, country: CountryCode, parent_id: int | None = None
):
    """Registration and profile form dropdowns - categories, domains, and so on."""
    items = master_service.lookup_dropdown(db, kind, country, parent_id)
    return ok("Master data loaded.", [item.model_dump() for item in items])


@router.get("/geography/areas")
def geography_areas(
    db: DbSession,
    country: CountryCode,
    level: int = Query(1, ge=1, le=4),
    parent_id: int | None = Query(None),
):
    items = master_service.area_dropdown(db, country, level, parent_id)
    return ok("Areas loaded.", [item.model_dump() for item in items])


@router.get("/geography/tree")
def geography_tree(
    db: DbSession, country: CountryCode, max_level: int = Query(2, ge=1, le=4)
):
    nodes = master_service.area_tree(db, country, max_level)
    return ok("Area tree loaded.", [node.model_dump() for node in nodes])


#: Upload folders holding participant documents (ID proof, certificates).
PRIVATE_FOLDERS = ("participants/",)

#: Types a browser may render inline. Anything else (including SVG and HTML,
#: which can carry script) is sent as a download.
INLINE_TYPES = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


@router.get("/files/{file_path:path}")
def download(
    file_path: str,
    db: DbSession,
    x_access_token: str | None = Header(None, alias="x-access-token"),
    x_auth_key: str | None = Header(None, alias="x-auth-key"),
):
    """Serve an uploaded file from storage.

    Catalogue and CMS assets (icons, images, product documents) are public.
    Participant documents need a signed-in administrator, or the participant
    who uploaded them.
    """
    file_path = normalise_upload_path(file_path)
    # Case-insensitive: Windows / macOS volumes treat "Participants/" as the same folder.
    if file_path.lower().startswith(PRIVATE_FOLDERS):
        file_access_service.assert_can_read(db, file_path, x_access_token, x_auth_key)
    content = read_file(file_path)
    filename = file_path.rsplit("/", 1)[-1]
    media_type = INLINE_TYPES.get(extension_of(filename))
    disposition = "inline" if media_type else "attachment"
    return Response(
        content=content,
        media_type=media_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/health", tags=["Health"])
def health(db: DbSession):
    """Liveness probe that also confirms the database is reachable."""
    from sqlalchemy import text

    db.execute(text("SELECT 1"))
    return ok(
        "Service is healthy.",
        {"env": settings.ENV, "version": settings.APP_VERSION, "database": "up"},
    )


@router.get("/partners/{partner_id}/jwks.json", include_in_schema=False)
def partner_jwks(partner_id: str, db: DbSession):
    """A partner's public keys (JWKS), read by OpenG2P Partner Management."""
    return partner_portal_service.jwks(db, partner_id)
