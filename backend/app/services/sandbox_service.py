"""Sandbox "try it" console.

Executes a catalogue endpoint against its configured upstream, records the
call in ``api_log`` and returns the response for the console to render.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urljoin

import httpx
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.catalog import Endpoint
from app.models.enums import Environment
from app.models.participant import Participant
from app.repositories.catalog_repository import (
    EndpointRepository,
    EndpointSchemaRepository,
)
from app.repositories.log_repository import ApiLogRepository
from app.schemas.catalog import TryItRequest, TryItResponse
from app.utils import schema_tools
from app.utils.common import generate_reference, safe_json, truncate

logger = get_logger(__name__)

#: Headers the console must not forward - they belong to the sandbox session,
#: not to the upstream call.
BLOCKED_REQUEST_HEADERS = {
    "x-access-token",
    "x-auth-key",
    "cookie",
    "host",
    "content-length",
}
MAX_LOGGED_BODY_CHARS = 8000


def execute(
    db: Session, participant: Participant, payload: TryItRequest
) -> TryItResponse:
    endpoint = _require_published_endpoint(db, payload.endpoint_id)
    _assert_environment_allowed(participant, payload.environment)

    # With no sandbox upstream configured, answer from the stored samples so
    # the console still works while the real service is not reachable.
    mock = payload.environment == Environment.SANDBOX and not _upstream_base(
        endpoint, payload.environment
    )
    target_url = (
        f"mock:{endpoint.endpoint_url}"
        if mock
        else _resolve_url(
            endpoint, payload.environment, payload.path_params, payload.query_params
        )
    )
    headers = _build_headers(payload.headers, participant, payload.environment)
    transaction_id = generate_reference("TXN")

    started_at = datetime.now(UTC)
    started = time.perf_counter()
    if mock:
        status_code, response_body, error_message = _mock_response(db, endpoint, payload)
        response_headers = {"content-type": "application/json", "x-sandbox-mock": "true"}
    else:
        status_code, response_headers, response_body, error_message = _call_upstream(
            endpoint.method or "GET", target_url, headers, payload.body
        )

    latency_ms = (time.perf_counter() - started) * 1000

    _record_call(
        db,
        endpoint=endpoint,
        participant=participant,
        environment=payload.environment,
        transaction_id=transaction_id,
        target_url=target_url,
        headers=headers,
        request_body=payload.body,
        status_code=status_code,
        response_body=response_body,
        latency_ms=latency_ms,
        started_at=started_at,
        error_message=error_message,
    )

    return TryItResponse(
        status_code=status_code,
        latency_ms=round(latency_ms, 2),
        headers=response_headers,
        body=response_body,
        request_url=target_url,
        transaction_id=transaction_id,
        error=error_message,
    )


def sample_request(db: Session, endpoint_id: int, status_code: str = "200") -> dict:
    """Pre-filled request body and headers for the console."""
    endpoint = _require_published_endpoint(db, endpoint_id)
    schema = EndpointSchemaRepository(db).get_for_status(endpoint_id, status_code)

    return {
        "endpoint_id": endpoint.endpoint_id,
        "method": endpoint.method,
        "path": endpoint.endpoint_url,
        "path_params": endpoint.path_params or (schema.path_params if schema else {}),
        "query_params": endpoint.query_params or {},
        "headers": _header_values(
            endpoint.header_params or (schema.header_json if schema else {})
        ),
        "body": endpoint.request_sample or (schema.req_json if schema else None),
        "request_schema": endpoint.request_schema
        or (schema.req_schema if schema else None),
        "response_schema": schema.res_schema if schema else None,
        "response_sample": schema.res_json if schema else None,
    }


def _header_values(params: dict[str, Any] | None) -> dict[str, str]:
    """Flatten stored header parameters into the ``name: value`` pairs a request sends.

    Imported specs store ``{name: {required, schema, description}}`` and the
    console editor stores ``{name: {value, required}}``; either way the
    console needs plain strings.
    """
    headers: dict[str, str] = {}
    for name, spec in (params or {}).items():
        if isinstance(spec, dict):
            value = spec.get("value", spec.get("example", ""))
        else:
            value = spec
        headers[name] = "" if value is None else str(value)
    return headers


def code_sample(
    db: Session, endpoint_id: int, language: str, environment: Environment
) -> dict:
    endpoint = _require_published_endpoint(db, endpoint_id)
    url = (
        _resolve_url(endpoint, environment, {}, {})
        if _upstream_base(endpoint, environment)
        # No upstream yet: show the path on a placeholder host rather than fail.
        else f"https://<{str(environment).lower()}-api-host>{endpoint.endpoint_url or ''}"
    )
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer <access_token>",
    }

    snippet = schema_tools.build_code_sample(
        language, endpoint.method or "GET", url, headers, endpoint.request_sample
    )
    return {"language": language, "code": snippet}


def convert_curl(command: str) -> dict:
    return schema_tools.parse_curl(command)


# ------------------------------------------------------------------ helpers
def _require_published_endpoint(db: Session, endpoint_id: int) -> Endpoint:
    endpoint = EndpointRepository(db).get(endpoint_id)
    if endpoint is None or not endpoint.is_published:
        raise NotFoundError("Endpoint not found.")
    return endpoint


def _assert_environment_allowed(
    participant: Participant, environment: Environment
) -> None:
    allowed = {
        Environment.SANDBOX: participant.is_sandbox_approved,
        Environment.UAT: participant.is_uat_approved,
        Environment.PRODUCTION: participant.is_prod_approved
        and participant.is_prod_enabled,
    }
    if not allowed.get(environment, False):
        raise ForbiddenError(
            f"Your account is not approved for the {environment} environment."
        )


def _resolve_url(
    endpoint: Endpoint,
    environment: Environment,
    path_params: dict[str, Any],
    query_params: dict[str, Any],
) -> str:
    base = _upstream_base(endpoint, environment)
    if not base:
        raise ValidationError(
            f"No {environment} upstream is configured for this endpoint."
        )

    path = _substitute_path_params(endpoint.endpoint_url or "", path_params)
    url = (
        path
        if path.startswith(("http://", "https://"))
        else urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    )

    if query_params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(query_params, doseq=True)}"
    return url


def _call_upstream(
    method: str, url: str, headers: dict[str, str], body: Any
) -> tuple[int, dict[str, str], Any, str | None]:
    try:
        with httpx.Client(
            timeout=settings.SANDBOX_PROXY_TIMEOUT, follow_redirects=True
        ) as client:
            response = client.request(
                method, url, headers=headers, json=body if body is not None else None
            )
    except httpx.TimeoutException:
        return 504, {}, None, "The upstream service did not respond in time."
    except httpx.HTTPError as exc:
        # The message can carry the upstream host; log it, do not return it.
        logger.warning("Sandbox call to %s failed: %s", url, exc)
        return 502, {}, None, "The upstream service could not be reached."
    return response.status_code, dict(response.headers), _decode_body(response), None


def _upstream_base(endpoint: Endpoint, environment: Environment) -> str | None:
    """Where a call is sent: the endpoint's own URL, else the API gateway.

    The gateway is used only for endpoints flagged as served through it (on
    the endpoint or its product); anything else without a URL stays in mock
    mode rather than being sent to a gateway that has no route for it.
    """
    base = {
        Environment.SANDBOX: endpoint.sandbox_api_url,
        Environment.UAT: endpoint.uat_api_url,
        Environment.PRODUCTION: endpoint.prod_api_url,
    }.get(environment)
    if base:
        return base
    if endpoint.is_gateway_published or endpoint.product.is_gateway_published:
        return gateway_url(environment)
    return None


def gateway_url(environment: Environment) -> str | None:
    """The gateway proxy URL configured for one environment, if any."""
    if not settings.GATEWAY_ENABLED:
        return None
    per_environment = {
        Environment.SANDBOX: settings.GATEWAY_SANDBOX_URL,
        Environment.UAT: settings.GATEWAY_UAT_URL,
        Environment.PRODUCTION: settings.GATEWAY_PROD_URL,
    }.get(environment)
    return per_environment or settings.GATEWAY_BASE_URL or None


def upstream_urls(endpoint: Endpoint) -> dict[str, str | None]:
    """Resolved upstream base per environment, for the admin console."""
    return {str(env): _upstream_base(endpoint, env) for env in Environment}


def _mock_response(
    db: Session, endpoint: Endpoint, payload: TryItRequest
) -> tuple[int, Any, str | None]:
    """Answer from the stored samples, like the reference's ``Sandbox_play_api``.

    Missing required headers or path parameters get the 401 sample; a body
    that matches one sample's request JSON gets that sample's response;
    anything else gets the 200 sample.
    """
    samples = [
        row
        for row in EndpointSchemaRepository(db).for_endpoint(endpoint.endpoint_id)
        if row.is_enabled
    ]
    by_status = {row.status_code: row for row in samples}

    supplied_headers = {key.lower(): value for key, value in (payload.headers or {}).items()}
    missing = [
        name
        for name, spec in (endpoint.header_params or {}).items()
        if isinstance(spec, dict)
        and spec.get("required")
        and not supplied_headers.get(name.lower())
    ] + [
        name
        for name, spec in (endpoint.path_params or {}).items()
        if isinstance(spec, dict)
        and spec.get("required")
        and not (payload.path_params or {}).get(name)
    ]
    if missing:
        sample = by_status.get("401")
        body = (
            sample.res_json
            if sample
            else {"errors": [{"code": "401", "message": "Required parameter missing."}]}
        )
        return 401, body, f"Missing required parameter(s): {', '.join(missing)}."

    if payload.body is not None:
        for row in samples:
            if row.req_json is not None and row.req_json == payload.body:
                return int(row.status_code), row.res_json, None

    sample = by_status.get("200") or (samples[0] if samples else None)
    if sample is None:
        return 404, None, "No response sample is configured for this endpoint."
    return int(sample.status_code), sample.res_json, None


def _substitute_path_params(path: str, params: dict[str, Any]) -> str:
    for key, value in (params or {}).items():
        path = path.replace(f"{{{key}}}", str(value))
    if "{" in path:
        missing = path[path.index("{") + 1 : path.index("}")] if "}" in path else "?"
        raise ValidationError(f"Path parameter '{missing}' is required.")
    return path


def _build_headers(
    supplied: dict[str, str], participant: Participant, environment: Environment
) -> dict[str, str]:
    headers = {
        key: value
        for key, value in (supplied or {}).items()
        if key.lower() not in BLOCKED_REQUEST_HEADERS
    }
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")

    entity_id = (
        participant.uat_entity_id
        if environment == Environment.UAT
        else participant.prod_entity_id
    )
    if entity_id:
        headers["x-entity-id"] = entity_id
    return headers


def _decode_body(response: httpx.Response) -> Any:
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return response.json()
        except ValueError:
            return response.text
    return truncate(response.text, MAX_LOGGED_BODY_CHARS)


def _record_call(
    db: Session,
    *,
    endpoint: Endpoint,
    participant: Participant,
    environment: Environment,
    transaction_id: str,
    target_url: str,
    headers: dict[str, str],
    request_body: Any,
    status_code: int,
    response_body: Any,
    latency_ms: float,
    started_at: datetime,
    error_message: str | None,
) -> None:
    try:
        ApiLogRepository(db).record(
            transaction_id=transaction_id,
            participant_id=participant.participant_id,
            entity_id=participant.uat_entity_id or participant.prod_entity_id,
            product_id=endpoint.product_id,
            endpoint_id=endpoint.endpoint_id,
            environment=str(environment),
            country_code=participant.country_code,
            method=endpoint.method,
            endpoint_url=endpoint.endpoint_url,
            target_url=target_url,
            status_code=status_code,
            error_message=error_message,
            request_time=started_at,
            response_time=datetime.now(UTC),
            latency_ms=round(latency_ms, 2),
            request_headers=_redact_headers(headers),
            request_body=safe_json(request_body),
            response_body=safe_json(response_body),
        )
    except Exception as exc:  # pragma: no cover - logging must not break the call
        logger.error("Failed to record sandbox call %s: %s", transaction_id, exc)
        db.rollback()


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Never persist credentials from the try-it form into the log table."""
    sensitive = {"authorization", "x-api-key", "x-api-secret", "proxy-authorization"}
    return {
        key: ("***" if key.lower() in sensitive else value)
        for key, value in headers.items()
    }
