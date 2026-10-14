"""Public endpoints - no authentication required."""

from __future__ import annotations

from fastapi import APIRouter, Header, Query
from fastapi.responses import Response

from app.config.settings import settings
from app.core.deps import CountryCode, DbSession, Locale
from app.core.responses import ok
from app.services import (
    catalog_service,
    content_service,
    file_access_service,
    master_service,
)
from app.utils.files import extension_of, read_file

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
    if file_path.lstrip("/").startswith(PRIVATE_FOLDERS):
        file_access_service.assert_can_read(
            db, file_path.lstrip("/"), x_access_token, x_auth_key
        )
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
