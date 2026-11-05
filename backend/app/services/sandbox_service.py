"""Sandbox "try it" console.

Executes a catalogue endpoint against its configured upstream, records the
call in ``api_log`` and returns the response for the console to render.
"""

from __future__ import annotations

import ipaddress
import json
import re
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.catalog import Endpoint
from app.models.enums import ApiCallSource, Environment
from app.models.participant import Participant
from app.repositories.catalog_repository import (
    EndpointRepository,
    EndpointSchemaRepository,
)
from app.repositories.log_repository import ApiLogRepository
from app.schemas.catalog import CodeSampleForm, TryItRequest, TryItResponse
from app.services import app_service
from app.utils import schema_tools
from app.utils.common import generate_reference, safe_json, truncate

logger = get_logger(__name__)

#: Headers the console must not forward (compared case-insensitively): the
#: sandbox session's own, hop-by-hop ones, and identity / client-address
#: headers an upstream may trust because the gateway normally sets them.
BLOCKED_REQUEST_HEADERS = {
    "x-access-token",
    "x-auth-key",
    "cookie",
    "host",
    "content-length",
    "connection",
    "keep-alive",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "proxy-authorization",
    "proxy-connection",
    "forwarded",
    "x-real-ip",
    "x-entity-id",
}
BLOCKED_REQUEST_HEADER_PREFIXES = ("x-forwarded-", "x-consumer-", "x-credential-")
MAX_LOGGED_BODY_CHARS = 8000
REDACTED = "***"
#: Header names, JSON / form keys and query parameters never stored in API history.
_SENSITIVE_NAME = re.compile(
    r"(pass(word)?|secret|token|api[-_]?key|apikey|authori[sz]ation|cookie|signature|"
    r"(^|[-_])(otp|pin)($|[-_])|credential|private[-_]?key)",
    re.IGNORECASE,
)
#: Sent with every try-it call; carries the call's API history transaction id.
SANDBOX_TRANSACTION_HEADER = "X-OAN-Sandbox-Transaction"


def execute(
    db: Session, participant: Participant, payload: TryItRequest, partner_token: str | None = None
) -> TryItResponse:
    """Run a try-it call. ``partner_token``: the participant's Keycloak access
    token, sent to a gateway that checks partner tokens (GATEWAY_PARTNER_AUTH=keycloak)."""
    endpoint = _require_published_endpoint(db, payload.endpoint_id)
    _assert_environment_allowed(participant, payload.environment)

    # Calls go to the gateway (or the endpoint's own upstream). Only with
    # SANDBOX_MOCK_RESPONSES on does a UAT endpoint without one answer from
    # its stored samples.
    mock = (
        settings.SANDBOX_MOCK_RESPONSES
        and payload.environment == Environment.UAT
        and not _upstream_base(endpoint, payload.environment)
    )
    target_url = (
        f"mock:{endpoint.endpoint_url}"
        if mock
        else _resolve_url(
            endpoint, payload.environment, payload.path_params, payload.query_params
        )
    )
    headers = _build_headers(payload.headers, participant, payload.environment)
    app_id = None
    if payload.app_id:
        # Call as one of the participant's apps: the gateway sees its API key
        # and applies that app's API product grants.
        headers = {
            k: v for k, v in headers.items() if k.lower() != settings.GATEWAY_APP_KEY_HEADER.lower()
        }
        if not partner_auth_by_app_token():
            headers[settings.GATEWAY_APP_KEY_HEADER] = app_service.try_it_key(
                db, participant, payload.app_id
            )
        # OAuth: the call sends the token in the form, as the partner would - the
        # one "Get token" fetched (POST /participant/apps/{id}/token) or one they
        # paste. No hidden token request: without one the gateway answers 401.
        app_id = app_service.owned_app_id(db, participant, payload.app_id)
    if partner_auth_by_token():
        # The gateway identifies the caller by its own Keycloak token, never by a
        # value typed into the form.
        token_header = settings.GATEWAY_PARTNER_TOKEN_HEADER
        headers = {k: v for k, v in headers.items() if k.lower() != token_header.lower()}
        if partner_token:
            headers[token_header] = partner_token
    transaction_id = generate_reference("TXN")
    # Identify sandbox traffic to the gateway and upstream: their access logs
    # then show which calls came from the sandbox, keyed by the same
    # transaction id as the participant's API history.
    headers.setdefault("User-Agent", f"OAN-Sandbox/{settings.APP_VERSION}")
    headers[SANDBOX_TRANSACTION_HEADER] = transaction_id

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
    # The participant sees (and API history keeps) the URL they can call themselves.
    shown_url = target_url if mock else public_url(target_url, payload.environment)

    _record_call(
        db,
        endpoint=endpoint,
        participant=participant,
        app_id=app_id,
        environment=payload.environment,
        transaction_id=transaction_id,
        target_url=shown_url,
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
        request_url=shown_url,
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
    db: Session,
    endpoint_id: int,
    language: str,
    environment: Environment,
    form: CodeSampleForm | None = None,
    participant: Participant | None = None,
) -> dict:
    """A copy-pasteable request: the published sample, or the try-it form as typed (``form``)."""
    endpoint = _require_published_endpoint(db, endpoint_id)
    base = _upstream_base(endpoint, environment)
    path = endpoint.endpoint_url or ""
    if form is not None:
        # Filled-in parameters replace their {placeholder}; empty ones stay visible.
        for key, value in form.path_params.items():
            if value not in (None, ""):
                path = path.replace(f"{{{key}}}", quote(str(value), safe=""))
    if not base:
        # No upstream yet: show the path on a placeholder host rather than fail.
        url = f"https://<{str(environment).lower()}-api-host>{path}"
    elif path.startswith(("http://", "https://")):
        url = path
    else:
        # Path parameters stay as {placeholders} for the caller to fill in.
        url = public_url(urljoin(base.rstrip("/") + "/", path.lstrip("/")), environment)
    if form is not None:
        query = {k: v for k, v in form.query_params.items() if v not in (None, "")}
        if query:
            url = f"{url}{'&' if '?' in url else '?'}{urlencode(query, doseq=True)}"
        declared = {k: v for k, v in form.headers.items() if k.strip()}
        body = form.body if form.has_body else None
    else:
        # The end-point's own headers (e.g. a CSRF header, a form Content-Type), so
        # the snippet runs as copied; the generic bearer header only when it
        # declares none.
        declared = _header_values(endpoint.header_params) or {
            "Authorization": "Bearer <access_token>"
        }
        body = endpoint.request_sample
    if partner_auth_by_token():
        # Where the participant gets it: oan-partner-api's token endpoint (see Credentials).
        token_header = settings.GATEWAY_PARTNER_TOKEN_HEADER
        declared = {k: v for k, v in declared.items() if k.lower() != token_header.lower()}
        declared[token_header] = "<partner access token>"
    if partner_auth_by_app_token():
        # OAuth: the app's access token, no key per call. Only this API's request:
        # the token request is its own snippet (the try-it page's "App token").
        # The token the form holds (from "Get token"), else a placeholder.
        token_header = settings.GATEWAY_PARTNER_TOKEN_HEADER
        typed = next(
            (v for k, v in declared.items() if k.lower() == token_header.lower() and v.strip()), None
        )
        declared = {
            k: v for k, v in declared.items()
            if k.lower() not in (token_header.lower(), settings.GATEWAY_APP_KEY_HEADER.lower())
        }
        declared[token_header] = typed or "<app access token>"
    elif form is not None and form.app_id and participant is not None:
        # The participant's own key, so the snippet runs as-is in Postman.
        key_header = settings.GATEWAY_APP_KEY_HEADER
        declared = {k: v for k, v in declared.items() if k.lower() != key_header.lower()}
        declared[key_header] = app_service.app_key(db, participant, form.app_id)
    if any(key.lower() == "content-type" for key in declared):
        headers = declared
    else:
        headers = {"Content-Type": "application/json", **declared}

    snippet = schema_tools.build_code_sample(
        language, endpoint.method or "GET", url, headers, body
    )
    return {"language": language, "code": snippet}


def partner_auth_by_app_token() -> bool:
    """The gateway identifies callers by their app's OAuth access token (client credentials)."""
    return settings.GATEWAY_PARTNER_AUTH == "oauth"


def partner_auth_by_token() -> bool:
    """The gateway identifies partners by their Keycloak access token."""
    return settings.GATEWAY_PARTNER_AUTH == "keycloak"


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
            f"This API is not served through the API gateway in {environment} yet."
        )

    path = _substitute_path_params(endpoint.endpoint_url or "", path_params)
    url = (
        path
        if path.startswith(("http://", "https://"))
        else urljoin(base.rstrip("/") + "/", path.lstrip("/"))
    )
    _assert_safe_target(url, base)

    if query_params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(query_params, doseq=True)}"
    return url


def _origin(url: str) -> tuple[str, str, int | None]:
    parts = urlsplit(url)
    port = parts.port or {"http": 80, "https": 443}.get(parts.scheme)
    return parts.scheme.lower(), (parts.hostname or "").lower(), port


def _assert_safe_target(url: str, base: str) -> None:
    """The call must stay on the configured upstream, and never reach internals.

    Relative endpoint paths must resolve under ``base`` (no ``..`` escape);
    an absolute endpoint URL must use the same origin as ``base``. Admin APIs
    of the gateway and Keycloak, and link-local / metadata addresses, are
    refused whatever the catalogue says.
    """
    target, upstream = urlsplit(url), urlsplit(base)
    if target.scheme not in ("http", "https") or not target.hostname:
        raise ValidationError("This end-point's upstream URL is not valid.")
    if _origin(url) != _origin(base):
        raise ValidationError("This end-point points outside its configured upstream.")
    base_path = upstream.path.rstrip("/")
    if base_path and not (target.path == base_path or target.path.startswith(base_path + "/")):
        raise ValidationError("This end-point points outside its configured upstream.")
    if "/../" in target.path + "/" or "/./" in target.path + "/":
        raise ValidationError("This end-point points outside its configured upstream.")
    _assert_not_internal(url)


def _assert_not_internal(url: str) -> None:
    scheme, host, port = _origin(url)
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_link_local or ip.is_multicast or ip.is_unspecified):
        raise ValidationError("This upstream address is not allowed.")
    for admin_url in (settings.GATEWAY_ADMIN_URL, settings.KEYCLOAK_URL):
        if admin_url and _origin(admin_url)[1:] == (host, port):
            if admin_url == settings.KEYCLOAK_URL and "/admin" not in urlsplit(url).path:
                continue  # Keycloak token endpoints are fine; its admin API is not.
            raise ValidationError("This upstream address is not allowed.")


def _call_upstream(
    method: str, url: str, headers: dict[str, str], body: Any
) -> tuple[int, dict[str, str], Any, str | None]:
    try:
        # Redirects are not followed: a 3xx from upstream could otherwise send
        # the server to an internal address and return what it finds there.
        with httpx.Client(
            timeout=settings.SANDBOX_PROXY_TIMEOUT, follow_redirects=False
        ) as client:
            if schema_tools.is_form_request(headers) and isinstance(body, dict):
                # e.g. an OAuth token endpoint: send the fields as a form.
                response = client.request(method, url, headers=headers, data=body)
            else:
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
        Environment.UAT: settings.GATEWAY_UAT_URL,
        Environment.PRODUCTION: settings.GATEWAY_PROD_URL,
    }.get(environment)
    return per_environment or settings.GATEWAY_BASE_URL or None


def public_url(url: str, environment: Environment) -> str:
    """``url`` with the gateway's internal address swapped for its public one.

    The API may reach the gateway on an address only it can use
    (``host.docker.internal``, a cluster service); participants copy URLs into
    Postman or their own code, so everything shown to them uses the public URL.
    """
    internal = gateway_url(environment)
    public = {
        Environment.UAT: settings.GATEWAY_UAT_PUBLIC_URL,
        Environment.PRODUCTION: settings.GATEWAY_PROD_PUBLIC_URL,
    }.get(environment)
    if not internal or not public:
        return url
    internal = internal.rstrip("/")
    if url == internal or url.startswith(internal + "/") or url.startswith(internal + "?"):
        return public.rstrip("/") + url[len(internal):]
    return url


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
        # Encoded as one path segment: "../" or "?" in a value cannot change
        # which route is called.
        path = path.replace(f"{{{key}}}", quote(str(value), safe=""))
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
        and not key.lower().startswith(BLOCKED_REQUEST_HEADER_PREFIXES)
        and "\n" not in str(value)
        and "\r" not in str(value)
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
    app_id: int | None,
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
            source=str(ApiCallSource.TRYIT),
            app_id=app_id,
            participant_id=participant.participant_id,
            entity_id=participant.uat_entity_id or participant.prod_entity_id,
            product_id=endpoint.product_id,
            endpoint_id=endpoint.endpoint_id,
            environment=str(environment),
            country_code=participant.country_code,
            method=endpoint.method,
            endpoint_url=endpoint.endpoint_url,
            target_url=_redact_url(target_url),
            status_code=status_code,
            error_message=error_message,
            request_time=started_at,
            response_time=datetime.now(UTC),
            latency_ms=round(latency_ms, 2),
            request_headers=_redact_headers(headers),
            request_body=_loggable(request_body),
            response_body=_loggable(response_body),
        )
    except Exception as exc:  # pragma: no cover - logging must not break the call
        logger.error("Failed to record sandbox call %s: %s", transaction_id, exc)
        db.rollback()


def _is_sensitive(name: str) -> bool:
    return bool(_SENSITIVE_NAME.search(name)) or name.lower() == settings.GATEWAY_APP_KEY_HEADER.lower()


def _redact_headers(headers: dict[str, str]) -> dict[str, str]:
    """Never persist credentials from the try-it form into the log table."""
    return {
        key: (REDACTED if _is_sensitive(key) else value) for key, value in headers.items()
    }


def redact_value(value: Any) -> Any:
    """``value`` with every sensitive key (password, token, secret...) masked, recursively."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if isinstance(key, str) and _is_sensitive(key) else redact_value(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    return value


def _redact_url(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    query = [
        (key, REDACTED if _is_sensitive(key) else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query, safe="*")))


def _loggable(body: Any) -> Any:
    """Redacted, size-capped copy of a request / response body for API history."""
    value = redact_value(safe_json(body))
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    if len(text) > MAX_LOGGED_BODY_CHARS:
        return {"truncated": True, "preview": truncate(text, MAX_LOGGED_BODY_CHARS)}
    return value
