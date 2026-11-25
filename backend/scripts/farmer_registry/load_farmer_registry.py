"""Load the Farmer Registry staff API into the OAN catalogue, served through the gateway.

Run from backend/ (reads deployment/farmer-registry/farmer_registry.postman_collection.json):
    venv\\Scripts\\python.exe scripts\\farmer_registry\\load_farmer_registry.py

The source is the registry team's Postman collection (staff API on the dev
environment plus a Keycloak token request). It has no OpenAPI spec, so the
collection is turned into one here and imported through the same service layer
as the admin console's "Import spec" action, into product
"Farmer Registry - Staff API" (category "Farmer Registry"). Every end-point is
flagged "served through the API gateway" with no upstream URL of its own, so
try-it calls go to GATEWAY_UAT_URL; the gateway routes ``/farmer-registry/*``
to the registry (see apisix-gateway/build_apisix_config.py). Safe to re-run.
"""

from __future__ import annotations

import json
import os
import re
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

#: Defaults to the copy in deployment/farmer-registry of this repository; inside a
#: container set FARMER_REGISTRY_COLLECTION_PATH (docker-compose mounts it).
COLLECTION = Path(
    os.getenv("FARMER_REGISTRY_COLLECTION_PATH")
    or Path(__file__).resolve().parents[3]
    / "deployment"
    / "farmer-registry"
    / "farmer_registry.postman_collection.json"
)
CATEGORY = "Farmer Registry"
PRODUCT = "Farmer Registry - Staff API"
#: Gateway path prefix; APISIX strips it before calling the registry.
PREFIX = "/farmer-registry"
TOKEN_PATH = f"{PREFIX}/auth/token"
#: The change-request controller depends on the section (is_core_section); the
#: collection switches between these two in a script, so both are published.
CHANGE_REQUEST_PATHS = {
    "/change-requests-core-data/create_change_request_for_core_data": "core-data sections",
    "/change-requests/create_change_request": "other sections",
}

BEARER = ("Authorization", f"Bearer <access_token from POST {TOKEN_PATH}>")
CSRF = ("X-CSRF-Token", "<any random value, e.g. a UUID>")
FORM = "application/x-www-form-urlencoded"

#: Collection variables that are filled in at run time by earlier requests:
#: shown as a hint of where the value comes from.
RUNTIME_HINTS = {
    "SUBJECT_INTERNAL_ID": "<internal_record_id from Search Farmer Register>",
    "TARGET_INTERNAL_ID": "<internal_record_id of the record, from Get Tab Records>",
    "CR_SECTION_REGISTER_ID": "<section_register_id from Get All Sections>",
    "SUBMISSION_ID": "<submission_id from Save Intake Form Submission>",
    "CR_NEW_MIDDLE_NAME": "Alemu",
    "INTAKE_FIRST_NAME": "Amina",
    "INTAKE_LAST_NAME": "Bekele",
}
DYNAMIC = {"$guid": "3f2b8c1e-7a4d-4e9b-9c2a-1d5e6f7a8b9c", "$isoTimestamp": "2026-10-22T09:30:00.000Z"}

AUTH_NOTE = (
    "Served through the API gateway. Get a token with POST /farmer-registry/auth/token "
    "(staff user of the registry's Keycloak), then send 'Authorization: Bearer <access_token>' "
    "and 'X-CSRF-Token: <any random value>' on every call; the gateway adds the matching "
    "CSRF cookie the registry expects."
)


def main() -> None:
    if not COLLECTION.exists():
        sys.exit(f"{COLLECTION} not found - set FARMER_REGISTRY_COLLECTION_PATH.")
    collection = json.loads(COLLECTION.read_text(encoding="utf-8"))
    spec = collection_to_openapi(collection)

    db = SessionLocal()
    admin_user = db.execute(
        select(AdmUser).where(AdmUser.is_master.is_(True)).order_by(AdmUser.admin_id)
    ).scalars().first()
    if admin_user is None:
        sys.exit("No master admin found - run `python -m app.seeds.seed` first.")
    admin = AdminPrincipal(user=admin_user, auth_key="script", permissions=set())

    product_id = _ensure_product(db, admin, _category(db, admin), collection)
    result = catalog_service.import_specification(
        db, admin, product_id, yaml.safe_dump(spec, sort_keys=False), replace_existing=False
    )

    operations = {
        (method.upper(), path): operation
        for path, item in spec["paths"].items()
        for method, operation in item.items()
    }
    endpoints = db.execute(
        select(Endpoint).where(Endpoint.product_id == product_id, Endpoint.is_deleted.is_(False))
    ).scalars().all()
    for endpoint in endpoints:
        operation = operations.get((endpoint.method, endpoint.endpoint_url))
        if operation is None:
            continue
        endpoint.uat_api_url = None  # use the gateway from .env
        endpoint.is_gateway_published = True
        endpoint.header_params = {
            param["name"]: {"required": True, "value": param["example"]}
            for param in operation.get("parameters", [])
            if param["in"] == "header"
        }
        endpoint.request_sample = _request_example(operation)
    db.commit()

    for endpoint in endpoints:
        if not endpoint.is_published:
            catalog_service.publish_endpoint(db, admin, endpoint.endpoint_id, True)
    catalog_service.publish_product(db, admin, product_id, True)

    gateway = settings.GATEWAY_UAT_URL or settings.GATEWAY_BASE_URL
    print(f"{PRODUCT}: {len(endpoints)} end-points ({result}), via gateway: {gateway or '(not configured)'}")
    if not settings.GATEWAY_ENABLED or not gateway:
        print("WARNING: set GATEWAY_ENABLED=true and GATEWAY_UAT_URL in .env, or try-it stays in mock mode.")
    db.close()


# ------------------------------------------------------------ collection -> OpenAPI
def collection_to_openapi(collection: dict) -> dict:
    variables = {v["key"]: v.get("value", "") for v in collection.get("variable", [])}
    paths: dict = {}
    for item in _requests(collection["item"]):
        request = item["request"]
        raw_url = request["url"]["raw"] if isinstance(request["url"], dict) else request["url"]
        title = re.sub(r"^\d+(\.\d+)*\s+", "", item["name"]).strip()
        description = (item.get("description") or request.get("description") or "").strip()

        if "/protocol/openid-connect/token" in raw_url:
            paths[TOKEN_PATH] = {"post": _token_operation(request, variables, title, description)}
            continue

        upstream_path = raw_url.replace("{{STAFF_API_BASE}}", "")
        body = _resolve(request.get("body", {}).get("raw") or "{}", variables)
        if upstream_path == "{{CR_CREATE_PATH}}":
            for path, sections in CHANGE_REQUEST_PATHS.items():
                paths[PREFIX + path] = {
                    "post": _staff_operation(f"{title} ({sections})", description, body)
                }
        else:
            paths[PREFIX + upstream_path] = {"post": _staff_operation(title, description, body)}

    return {
        "openapi": "3.0.3",
        "info": {
            "title": PRODUCT,
            "version": "1.0.0",
            "description": collection["info"].get("description") or "Farmer Registry staff API.",
        },
        "paths": paths,
    }


def _requests(items: list[dict]):
    for item in items:
        if "item" in item:
            yield from _requests(item["item"])
        else:
            yield item


def _resolve(text: str, variables: dict[str, str]) -> object:
    """Fill {{variables}} in a raw JSON body with sample values and parse it."""

    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in DYNAMIC:
            return DYNAMIC[name]
        if name in RUNTIME_HINTS:
            return RUNTIME_HINTS[name]
        return str(variables.get(name, ""))

    # SUBMISSION_ID_JSON is a bare JSON value (null starts a new submission).
    text = text.replace("{{SUBMISSION_ID_JSON}}", "null")
    return json.loads(re.sub(r"\{\{([^}]+)\}\}", value, text))


def _staff_operation(title: str, description: str, body: object) -> dict:
    return {
        "summary": title,
        "description": (description + "\n\n" + AUTH_NOTE).strip(),
        "parameters": [
            {"name": name, "in": "header", "required": True, "schema": {"type": "string"}, "example": example}
            for name, example in (BEARER, CSRF)
        ],
        "requestBody": {"required": True, "content": {"application/json": {"example": body}}},
        "responses": {
            "200": _response(
                "Success. Validation failures also answer 200, with response_status ERROR.",
                _envelope("SUCCESS", None, None, {}),
            ),
            "401": _response(
                "Missing, invalid or expired bearer token.",
                _envelope("ERROR", "G2P-AUT-401", "Unauthorized. Jwt expired. JWTError('Error decoding token claims.')"),
            ),
            "403": _response(
                "X-CSRF-Token header missing.",
                _envelope("ERROR", "G2P-AUT-403", "Forbidden. CSRF token missing or invalid."),
            ),
        },
    }


def _token_operation(request: dict, variables: dict[str, str], title: str, description: str) -> dict:
    fields = {entry["key"]: entry.get("value", "") for entry in request["body"].get("urlencoded", [])}
    sample = {
        **fields,
        "client_id": variables.get("OIDC_CLIENT_ID", ""),
        "client_secret": "<client secret>",
        "username": "<staff username>",
        "password": "<staff password>",
    }
    return {
        "summary": title.replace("(Keycloak password grant)", "").strip() or "Get Access Token",
        "description": (
            "Keycloak password grant for a staff user of the Farmer Registry. Use the returned "
            "access_token as 'Authorization: Bearer <access_token>' on the other end-points. "
            "Ask the registry team for a staff user and the client secret."
        ),
        "parameters": [
            {"name": "Content-Type", "in": "header", "required": True, "schema": {"type": "string"}, "example": FORM}
        ],
        "requestBody": {"required": True, "content": {FORM: {"example": sample}}},
        "responses": {
            "200": _response("Token issued.", {
                "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.sandbox.example",
                "expires_in": 300,
                "refresh_expires_in": 1800,
                "token_type": "Bearer",
                "scope": "openid profile email",
            }),
            "401": _response("Wrong client secret or user credentials.", {
                "error": "unauthorized_client",
                "error_description": "Invalid client or Invalid client credentials",
            }),
        },
    }


def _envelope(status: str, code: str | None, message: str | None, payload: object = None) -> dict:
    """The registry's response envelope (as answered by the dev staff API)."""
    return {
        "response_header": {
            "request_id": DYNAMIC["$guid"],
            "response_status": status,
            "response_error_code": code,
            "response_error_message": message,
            "response_timestamp": "2026-10-22T09:30:00.000000",
        },
        "response_body": {"pagination_response": None, "response_payload": payload},
    }


def _response(description: str, example: object) -> dict:
    return {"description": description, "content": {"application/json": {"example": example}}}


def _request_example(operation: dict) -> object:
    content = operation.get("requestBody", {}).get("content", {})
    return next(iter(content.values()), {}).get("example")


# ------------------------------------------------------------ catalogue rows
def _category(db, admin) -> int:
    row = db.execute(
        select(ProductCategory).where(
            ProductCategory.category_name == CATEGORY, ProductCategory.is_deleted.is_(False)
        )
    ).scalars().first()
    if row is not None:
        return row.category_id
    return master_service.create_product_category(
        db, admin, ProductCategoryCreate(category_name=CATEGORY, description="Farmer registry APIs.")
    ).category_id


def _ensure_product(db, admin, category_id: int, collection: dict) -> int:
    values = {
        "display_name": "Farmer Registry",
        "description": (
            "Search farmers, read a farmer's record, raise change requests and register new "
            "farmers through intake forms on the Farmer Registry staff API. " + AUTH_NOTE
        ),
        "category_id": category_id,
        "api_doc_version": "1.0.0",
        "product_keywords": ["Farmer Registry", "OpenG2P", "Staff API", "Intake", "Change Request"],
        "is_gateway_published": True,
    }
    existing = db.execute(
        select(Product).where(Product.product_name == PRODUCT, Product.is_deleted.is_(False))
    ).scalars().first()
    if existing is None:
        return catalog_service.create_product(db, admin, ProductCreate(product_name=PRODUCT, **values)).product_id
    catalog_service.update_product(db, admin, ProductUpdate(product_id=existing.product_id, **values))
    return existing.product_id


if __name__ == "__main__":
    main()
