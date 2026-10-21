"""Load the A2C (Access to Credit) API into the OAN catalogue, one product per domain.

Run from backend/ (reads deployment/a2c/openapi_v1.public.yaml):
    venv\\Scripts\\python.exe scripts\\a2c\\load_a2c.py

A2C's ``openapi_v1.public.yaml`` groups its operations into domains (tags),
the same D01..D11 split its Kong routes are tagged with. Each domain becomes a
product in the "Access to Credit (A2C)" category, imported through the same
service layer as the admin console's "Import spec" action. Every product is
flagged "served through the API gateway" and its end-points carry no upstream
URL of their own, so try-it calls go to the gateway configured in .env
(GATEWAY_ENABLED / GATEWAY_SANDBOX_URL, the local Kong proxy). The credential
header Kong expects is pre-filled on each end-point. Safe to re-run.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import yaml  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.deps import AdminPrincipal  # noqa: E402
from app.models.admin import AdmUser  # noqa: E402
from app.models.catalog import Endpoint, Product  # noqa: E402
from app.models.masters import ProductCategory  # noqa: E402
from app.schemas.catalog import ProductCreate, ProductUpdate  # noqa: E402
from app.schemas.masters import ProductCategoryCreate  # noqa: E402
from app.services import catalog_service, master_service  # noqa: E402

#: A2C OpenAPI spec. Defaults to the copy in deployment/a2c of this repository;
#: inside a container set A2C_SPEC_PATH (docker-compose mounts it).
SPEC = Path(
    os.getenv("A2C_SPEC_PATH")
    or Path(__file__).resolve().parents[3] / "deployment" / "a2c" / "openapi_v1.public.yaml"
)
CATEGORY = "Access to Credit (A2C)"
PRODUCT_PREFIX = "A2C - "
#: The single all-in-one product of the first load, retired in favour of per-domain products.
RETIRED_PRODUCTS = ["OAN Access to Credit (A2C)"]
LOGIN_SAMPLE = {"usr": "farmer@a2c.test", "pwd": "Test@1234", "remember_me": False}

#: Credential header per OpenAPI security scheme, as Kong enforces it
#: (A2C kong.yml: jwt on Authorization, key-auth on ``apikey``).
SCHEME_HEADERS = {
    "BearerAuth": ("Authorization", "Bearer <token from POST /v1/auth/login>"),
    "PartnerApiKeyAuth": ("apikey", "<partner API key>"),
    "DashboardKeyAuth": ("apikey", "<dashboards API key>"),
}
AUTH_NOTE = (
    " Served through the Kong API gateway: sign in with POST /v1/auth/login "
    "(A2C - Identity & Access) and send 'Authorization: Bearer <token>'."
)


def main() -> None:
    if not SPEC.exists():
        sys.exit(f"{SPEC} not found - set A2C_SPEC_PATH to the A2C openapi_v1.public.yaml.")
    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))

    db = SessionLocal()
    admin_user = db.execute(
        select(AdmUser).where(AdmUser.is_master.is_(True)).order_by(AdmUser.admin_id)
    ).scalars().first()
    if admin_user is None:
        sys.exit("No master admin found - run `python -m app.seeds.seed` first.")
    admin = AdminPrincipal(user=admin_user, auth_key="script", permissions=set())

    for name in RETIRED_PRODUCTS:
        old = _product(db, name)
        if old is not None:
            if old.is_published:
                catalog_service.publish_product(db, admin, old.product_id, False)
            catalog_service.delete_product(db, admin, old.product_id)
            print(f"retired product '{name}'")

    category_id = _category(db, admin)
    security = _credential_headers(spec)

    total = 0
    for order, tag in enumerate(spec["tags"], start=1):
        domain_spec = _spec_for_tag(spec, tag["name"])
        if not domain_spec["paths"]:
            continue
        product_id = _ensure_product(db, admin, tag, order, category_id, spec)
        result = catalog_service.import_specification(
            db, admin, product_id, yaml.safe_dump(domain_spec, sort_keys=False), replace_existing=False
        )

        endpoints = db.execute(
            select(Endpoint).where(Endpoint.product_id == product_id, Endpoint.is_deleted.is_(False))
        ).scalars().all()
        for endpoint in endpoints:
            endpoint.sandbox_api_url = None  # use the gateway from .env
            endpoint.is_gateway_published = True
            headers = {
                name: value
                for name, value in (endpoint.header_params or {}).items()
                if name not in ("Authorization", "apikey")
            }
            credential = security.get((endpoint.method, endpoint.endpoint_url))
            if credential:
                headers[credential[0]] = {"required": True, "value": credential[1]}
            endpoint.header_params = headers
            if (endpoint.method, endpoint.endpoint_url) == ("POST", "/v1/auth/login"):
                endpoint.request_sample = LOGIN_SAMPLE
        db.commit()

        for endpoint in endpoints:
            if not endpoint.is_published:
                catalog_service.publish_endpoint(db, admin, endpoint.endpoint_id, True)
        catalog_service.publish_product(db, admin, product_id, True)
        total += len(endpoints)
        print(f"  {PRODUCT_PREFIX}{tag['name']}: {len(endpoints)} end-points ({result})")

    gateway = settings.GATEWAY_SANDBOX_URL or settings.GATEWAY_BASE_URL
    print(f"{total} end-points in category '{CATEGORY}', via gateway: {gateway or '(not configured)'}")
    if not settings.GATEWAY_ENABLED or not gateway:
        print("WARNING: set GATEWAY_ENABLED=true and GATEWAY_SANDBOX_URL in .env, or try-it stays in mock mode.")
    db.close()


def _product(db, name: str) -> Product | None:
    return db.execute(
        select(Product).where(Product.product_name == name, Product.is_deleted.is_(False))
    ).scalars().first()


def _category(db, admin) -> int:
    row = db.execute(
        select(ProductCategory).where(
            ProductCategory.category_name == CATEGORY, ProductCategory.is_deleted.is_(False)
        )
    ).scalars().first()
    if row is not None:
        return row.category_id
    return master_service.create_product_category(
        db,
        admin,
        ProductCategoryCreate(
            category_name=CATEGORY,
            description="Open Agri Net Access to Credit: farmers, banks, loan products and applications.",
        ),
    ).category_id


def _ensure_product(db, admin, tag: dict, order: int, category_id: int, spec: dict) -> int:
    values = {
        "display_name": tag["name"],
        "description": (tag.get("description") or "").strip() + AUTH_NOTE,
        "category_id": category_id,
        "api_doc_version": str(spec["info"]["version"]),
        "sort_order": order,
        "product_keywords": ["A2C", "Access to Credit", tag["name"]],
        "is_gateway_published": True,
    }
    existing = _product(db, PRODUCT_PREFIX + tag["name"])
    if existing is None:
        return catalog_service.create_product(
            db, admin, ProductCreate(product_name=PRODUCT_PREFIX + tag["name"], **values)
        ).product_id
    catalog_service.update_product(
        db, admin, ProductUpdate(product_id=existing.product_id, **values)
    )
    return existing.product_id


def _spec_for_tag(spec: dict, tag: str) -> dict:
    """The full document restricted to one tag's operations (components kept for $refs)."""
    paths = {}
    for path, operations in spec["paths"].items():
        kept = {
            method: op
            for method, op in operations.items()
            if not isinstance(op, dict) or "tags" not in op or tag in op["tags"]
        }
        if any(isinstance(op, dict) and tag in op.get("tags", []) for op in kept.values()):
            paths[path] = {m: op for m, op in kept.items() if not isinstance(op, dict) or tag in op.get("tags", [])}
    return {
        **spec,
        "info": {**spec["info"], "title": f"{spec['info']['title']} - {tag}"},
        "tags": [t for t in spec["tags"] if t["name"] == tag],
        "paths": paths,
    }


def _credential_headers(spec: dict) -> dict[tuple[str, str], tuple[str, str] | None]:
    default_security = spec.get("security") or []
    out = {}
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if not isinstance(operation, dict):
                continue
            names = [n for requirement in operation.get("security", default_security) for n in requirement]
            out[(method.upper(), path)] = SCHEME_HEADERS.get(names[0]) if names else None
    return out


if __name__ == "__main__":
    main()
