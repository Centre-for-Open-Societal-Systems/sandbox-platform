"""Downloadable API contract: an OpenAPI 3.0 document per product.

Built from the published catalogue (end-points, their parameters, request
and response schemas and samples). Credentials are never included: the
documents name the auth scheme the gateway uses (``GATEWAY_PARTNER_AUTH``)
and never hold a key or a secret.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.integrations import keycloak
from app.models.catalog import Endpoint, EndpointSchema, Product
from app.models.enums import Environment
from app.repositories.catalog_repository import (
    EndpointRepository,
    EndpointSchemaRepository,
)
from app.services import catalog_service, sandbox_service
from app.utils import schema_tools

_PLACEHOLDER = re.compile(r"\{([^{}/]+)\}")
#: Sent by the caller's HTTP client or covered by the security scheme; not documented as parameters.
_SKIPPED_HEADERS = {"authorization", "content-type", "content-length", "accept", "host"}

EndpointRows = list[tuple[Endpoint, list[EndpointSchema]]]


# ------------------------------------------------------------------ public
def openapi_document(db: Session, product_id: int, environment: Environment = Environment.UAT) -> dict:
    """OpenAPI 3.0.3 for the published end-points of one published product."""
    product, rows = _load(db, product_id)
    return build_openapi(product, rows, environment)


def _load(db: Session, product_id: int) -> tuple[Product, EndpointRows]:
    # Same visibility rule as the catalogue pages (404 for an unpublished product).
    catalog_service.get_product(db, product_id, published_only=True)
    product = db.get(Product, product_id)
    schemas = EndpointSchemaRepository(db)
    endpoints = EndpointRepository(db).for_product(product_id, published_only=True)
    return product, [(endpoint, schemas.for_endpoint(endpoint.endpoint_id)) for endpoint in endpoints]


# ----------------------------------------------------------------- helpers
def _auth() -> dict[str, str]:
    """Header (and how to fill it) the gateway expects for the configured partner auth."""
    if settings.GATEWAY_PARTNER_AUTH == "apikey":
        return {
            "header": settings.GATEWAY_APP_KEY_HEADER,
            "variable": "apiKey",
            "description": (
                "The API key of your app (My Apps). Apps with a secret may sign requests with "
                "HMAC instead; the key goes in this header either way."
            ),
        }
    return {
        "header": settings.GATEWAY_PARTNER_TOKEN_HEADER,
        "variable": "accessToken",
        "description": (
            "Access token of your app (OAuth client credentials: your API key as client id and your secret)."
            if settings.GATEWAY_PARTNER_AUTH == "oauth"
            else "Access token from your sandbox sign-in (Keycloak)."
        ),
    }


def _token_url(environment: Environment) -> str | None:
    if settings.GATEWAY_PARTNER_AUTH != "oauth":
        return None
    try:
        with keycloak.use_realm(keycloak.realm_for(str(environment))):
            return keycloak.token_url()
    except Exception:  # noqa: BLE001 - Keycloak not configured: the document just omits the URL
        return None


def _split(endpoint: Endpoint, environment: Environment) -> tuple[str, str]:
    """(base URL, path) of an end-point; the base is a placeholder host when it has no upstream yet."""
    path = endpoint.endpoint_url or "/"
    if path.startswith(("http://", "https://")):
        parts = urlsplit(path)
        return f"{parts.scheme}://{parts.netloc}", parts.path or "/"
    base = sandbox_service.endpoint_base_url(endpoint, environment)
    if not base:
        base = f"https://<{str(environment).lower()}-api-host>"
    return base, "/" + path.lstrip("/")


def _common_base(bases: list[str], default: str) -> str:
    return Counter(bases).most_common(1)[0][0] if bases else default


def _fields(spec: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Parameter definitions as stored: ``{name: {required, schema, description, value|example}}``."""
    rows = []
    for name, raw in (spec or {}).items():
        raw = raw if isinstance(raw, dict) else {"value": raw}
        value = raw.get("value", raw.get("example"))
        rows.append(
            {
                "name": name,
                "required": bool(raw.get("required", False)),
                "schema": raw.get("schema") if isinstance(raw.get("schema"), dict) else {"type": "string"},
                "description": raw.get("description"),
                "value": "" if value is None else str(value),
            }
        )
    return rows


def _success_schema(schemas: list[EndpointSchema]) -> EndpointSchema | None:
    return next((s for s in schemas if s.status_code == "200"), schemas[0] if schemas else None)


def _request_parts(endpoint: Endpoint, schemas: list[EndpointSchema]):
    """(path, query, header fields, body schema, body sample, is_form) of one end-point."""
    primary = _success_schema(schemas)
    header_spec = endpoint.header_params or (primary.header_json if primary else None)
    declared = {
        k: v.get("value", v.get("example", "")) if isinstance(v, dict) else v
        for k, v in (header_spec or {}).items()
    }
    headers = [h for h in _fields(header_spec) if h["name"].lower() not in _SKIPPED_HEADERS]
    return (
        _fields(endpoint.path_params or (primary.path_params if primary else None)),
        _fields(endpoint.query_params),
        headers,
        endpoint.request_schema or (primary.req_schema if primary else None),
        endpoint.request_sample or (primary.req_json if primary else None),
        schema_tools.is_form_request(declared),
    )


def _operation_id(method: str, path: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", f"{method.lower()} {path}").strip("_") or method.lower()
    name, n = base, 2
    while name in used:
        name, n = f"{base}_{n}", n + 1
    used.add(name)
    return name


# ----------------------------------------------------------------- OpenAPI
def build_openapi(product: Product, rows: EndpointRows, environment: Environment = Environment.UAT) -> dict:
    auth = _auth()
    split = [_split(endpoint, environment) for endpoint, _ in rows]
    base = _common_base([b for b, _ in split], f"https://<{str(environment).lower()}-api-host>")
    title = product.display_name or product.product_name
    used: set[str] = set()
    paths: dict[str, dict] = {}

    for (endpoint, schemas), (op_base, path) in zip(rows, split, strict=True):
        method = (endpoint.method or "GET").lower()
        path_fields, query_fields, header_fields, body_schema, body_sample, is_form = _request_parts(
            endpoint, schemas
        )
        declared_path = {f["name"]: f for f in path_fields}
        parameters = []
        for name in _PLACEHOLDER.findall(path):
            parameters.append(_parameter(declared_path.get(name, {"name": name}), "path", required=True))
        parameters += [_parameter(f, "query") for f in query_fields]
        parameters += [_parameter(f, "header") for f in header_fields]

        operation: dict[str, Any] = {
            "operationId": _operation_id(method, path, used),
            "summary": endpoint.display_name or f"{method.upper()} {path}",
            "tags": [title],
            "responses": _responses(schemas),
        }
        if endpoint.description:
            operation["description"] = endpoint.description
        if parameters:
            operation["parameters"] = parameters
        if body_schema or body_sample is not None:
            media = "application/x-www-form-urlencoded" if is_form else "application/json"
            content: dict[str, Any] = {"schema": body_schema or schema_tools.infer_schema(body_sample)}
            if body_sample is not None:
                content["example"] = body_sample
            operation["requestBody"] = {"content": {media: content}}
        if op_base != base:
            operation["servers"] = [{"url": op_base}]
        paths.setdefault(path, {})[method] = operation

    description = product.description or ""
    token_url = _token_url(environment)
    if token_url:
        description = f"{description}\n\nToken URL (client credentials): {token_url}".strip()
    return {
        "openapi": "3.0.3",
        "info": {
            "title": title,
            "version": product.api_doc_version or "1.0.0",
            **({"description": description} if description else {}),
        },
        "servers": [{"url": base, "description": f"OAN {str(environment).title()} gateway"}],
        "tags": [{"name": title}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "PartnerAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": auth["header"],
                    "description": auth["description"],
                }
            }
        },
        "security": [{"PartnerAuth": []}],
    }


def _parameter(field: dict[str, Any], location: str, required: bool | None = None) -> dict[str, Any]:
    param: dict[str, Any] = {
        "name": field["name"],
        "in": location,
        "required": field.get("required", False) if required is None else required,
        "schema": field.get("schema") or {"type": "string"},
    }
    if field.get("description"):
        param["description"] = field["description"]
    if field.get("value"):
        param["example"] = field["value"]
    return param


def _responses(schemas: list[EndpointSchema]) -> dict[str, Any]:
    if not schemas:
        return {"200": {"description": "Success"}}
    responses: dict[str, Any] = {}
    for item in schemas:
        response: dict[str, Any] = {"description": f"Response {item.status_code}"}
        if item.res_schema or item.res_json is not None:
            content: dict[str, Any] = {"schema": item.res_schema or schema_tools.infer_schema(item.res_json)}
            if item.res_json is not None:
                content["example"] = item.res_json
            response["content"] = {"application/json": content}
        responses[str(item.status_code)] = response
    return responses
