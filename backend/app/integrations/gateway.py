"""Read services and routes from the API gateway's Admin API.

Two gateways are supported, picked with ``GATEWAY_TYPE``: Apache APISIX
(``/apisix/admin/services``, ``/apisix/admin/routes``) and Kong
(``/services``, ``/routes``, ``/plugins``). Both are reduced to the same
:class:`GatewayService` / :class:`GatewayRoute` records, with paths written
the OpenAPI way (``/v1/leads/{id}``), so the catalogue sync does not depend
on the gateway product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config.settings import settings
from app.core.exceptions import UpstreamError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Methods that describe an API operation; OPTIONS / HEAD routes are plumbing.
OPERATION_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")

_APISIX_PARAM = re.compile(r"/:([A-Za-z_][A-Za-z0-9_]*)")
_KONG_NAMED_GROUP = re.compile(r"\(\?<([A-Za-z_][A-Za-z0-9_]*)>\[\^/\]\+\)")
_REGEX_CHARS = re.compile(r"[()\[\]\\^$+?*|.]")


@dataclass(slots=True)
class GatewayService:
    #: Stable identity, stored on the catalogue product: "<type>:<service id>".
    key: str
    name: str
    description: str | None = None


@dataclass(slots=True)
class GatewayRoute:
    name: str
    service_key: str | None
    #: OpenAPI-style paths; untranslatable ones are listed in ``skipped``.
    paths: list[str]
    methods: list[str]
    description: str | None = None
    #: Credential header the gateway (or, by label, the upstream) expects.
    auth_header: str | None = None
    auth_hint: str | None = None
    skipped: list[str] = field(default_factory=list)
    #: The gateway's own route id (what a consumer's route whitelist names).
    id: str = ""
    #: API key header (``key-auth``) the route also checks next to ``auth_header``,
    #: e.g. a sandbox app key on top of a user's bearer token.
    key_header: str | None = None


@dataclass(slots=True)
class GatewaySnapshot:
    gateway_type: str
    services: list[GatewayService]
    routes: list[GatewayRoute]


def is_configured() -> bool:
    return bool(settings.GATEWAY_SYNC_ENABLED and settings.GATEWAY_ADMIN_URL)


def fetch() -> GatewaySnapshot:
    """Read the configured gateway. Raises when sync is off or the gateway fails."""
    if not settings.GATEWAY_SYNC_ENABLED:
        raise ValidationError("Pulling from the API gateway is disabled (GATEWAY_SYNC_ENABLED).")
    if not settings.GATEWAY_ADMIN_URL:
        raise ValidationError("GATEWAY_ADMIN_URL is not set.")
    reader = _read_apisix if settings.GATEWAY_TYPE == "apisix" else _read_kong
    try:
        with httpx.Client(
            base_url=settings.GATEWAY_ADMIN_URL.rstrip("/"),
            timeout=settings.GATEWAY_ADMIN_TIMEOUT,
            headers=_admin_headers(),
        ) as client:
            return reader(client)
    except httpx.HTTPStatusError as exc:
        logger.warning("Gateway Admin API answered %s: %s", exc.response.status_code, exc)
        raise UpstreamError(
            f"The {settings.GATEWAY_TYPE} Admin API answered HTTP {exc.response.status_code}."
            " Check GATEWAY_ADMIN_URL and GATEWAY_ADMIN_TOKEN."
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("Gateway Admin API unreachable: %s", exc)
        raise UpstreamError(
            f"The {settings.GATEWAY_TYPE} Admin API could not be reached at GATEWAY_ADMIN_URL."
        ) from exc


def _admin_headers() -> dict[str, str]:
    token = settings.GATEWAY_ADMIN_TOKEN
    if not token:
        return {}
    return {"X-API-KEY": token} if settings.GATEWAY_TYPE == "apisix" else {"Kong-Admin-Token": token}


# ---------------------------------------------------------------- APISIX
def _read_apisix(client: httpx.Client) -> GatewaySnapshot:
    services = {
        item["id"]: item for item in _apisix_list(client, "/apisix/admin/services")
    }
    routes = []
    for route in _apisix_list(client, "/apisix/admin/routes"):
        service = services.get(route.get("service_id")) or {}
        uris = route.get("uris") or ([route["uri"]] if route.get("uri") else [])
        paths, skipped = [], []
        for uri in uris:
            path = apisix_uri_to_path(uri)
            (paths if path else skipped).append(path or uri)
        plugins = {**(service.get("plugins") or {}), **(route.get("plugins") or {})}
        auth_header, auth_hint = _auth_from_plugins(plugins, route.get("labels") or {})
        routes.append(
            GatewayRoute(
                id=str(route["id"]),
                name=route.get("name") or route["id"],
                service_key=f"apisix:{route['service_id']}" if route.get("service_id") else None,
                paths=paths,
                methods=[m.upper() for m in route.get("methods") or []],
                description=route.get("desc"),
                auth_header=auth_header,
                auth_hint=auth_hint,
                skipped=skipped,
                key_header=_key_header(plugins),
            )
        )
    return GatewaySnapshot(
        gateway_type="apisix",
        services=[
            GatewayService(key=f"apisix:{sid}", name=item.get("name") or sid, description=item.get("desc"))
            for sid, item in services.items()
        ],
        routes=routes,
    )


def _apisix_list(client: httpx.Client, path: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        response = client.get(path, params={"page": page, "page_size": 500})
        response.raise_for_status()
        body = response.json()
        chunk = [entry["value"] for entry in body.get("list") or [] if entry.get("value")]
        items.extend(chunk)
        if len(items) >= int(body.get("total") or 0) or not chunk:
            return items
        page += 1


_PATH_PARAM = re.compile(r"\{([^}]+)\}")


def operation_key(method: str | None, path: str | None) -> tuple[str, str]:
    """Method + path with parameter names blanked: '{id}' and '{leadId}' match."""
    return (method or "").upper(), _PATH_PARAM.sub("{}", (path or "").rstrip("/") or "/")


def apisix_uri_to_path(uri: str) -> str | None:
    """'/v1/leads/:id/status' -> '/v1/leads/{id}/status'; wildcards are not operations."""
    if "*" in uri:
        return None
    return _APISIX_PARAM.sub(lambda m: "/{" + m.group(1) + "}", uri)


# ------------------------------------------------------------------ Kong
def _read_kong(client: httpx.Client) -> GatewaySnapshot:
    services = {item["id"]: item for item in _kong_list(client, "/services")}
    plugins = [p for p in _kong_list(client, "/plugins") if p.get("enabled", True)]
    routes = []
    for route in _kong_list(client, "/routes"):
        service_id = (route.get("service") or {}).get("id")
        attached = {
            p["name"]: p.get("config") or {}
            for p in plugins
            if (p.get("service") or {}).get("id") == service_id and not p.get("route")
        } | {
            p["name"]: p.get("config") or {}
            for p in plugins
            if (p.get("route") or {}).get("id") == route["id"]
        }
        paths, skipped = [], []
        for kong_path in route.get("paths") or []:
            path = kong_path_to_path(kong_path)
            (paths if path else skipped).append(path or kong_path)
        auth_header, auth_hint = _auth_from_plugins(attached, {})
        routes.append(
            GatewayRoute(
                id=str(route["id"]),
                name=route.get("name") or route["id"],
                service_key=f"kong:{service_id}" if service_id else None,
                paths=paths,
                methods=[m.upper() for m in route.get("methods") or []],
                description=None,
                auth_header=auth_header,
                auth_hint=auth_hint,
                skipped=skipped,
            )
        )
    return GatewaySnapshot(
        gateway_type="kong",
        services=[
            GatewayService(key=f"kong:{sid}", name=item.get("name") or sid)
            for sid, item in services.items()
        ],
        routes=routes,
    )


def _kong_list(client: httpx.Client, path: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    next_page: str | None = f"{path}?size=1000"
    while next_page:
        response = client.get(next_page)
        response.raise_for_status()
        body = response.json()
        items.extend(body.get("data") or [])
        next_page = body.get("next")
    return items


def kong_path_to_path(path: str) -> str | None:
    """'~/v1/leads/(?<id>[^/]+)$' -> '/v1/leads/{id}'; '/v1/me' stays as is."""
    if not path.startswith("~"):
        return path
    body = path[1:].removesuffix("$")
    body = _KONG_NAMED_GROUP.sub(lambda m: "{" + m.group(1) + "}", body)
    if _REGEX_CHARS.search(body.replace("{", "").replace("}", "")):
        return None
    return body


# ---------------------------------------------------------------- shared
def _key_header(plugins: dict[str, Any]) -> str | None:
    if "key-auth" not in plugins:
        return None
    config = plugins["key-auth"] or {}
    return config.get("header") or (config.get("key_names") or ["apikey"])[0]


def _auth_from_plugins(plugins: dict[str, Any], labels: dict[str, Any]) -> tuple[str | None, str | None]:
    """Credential header a caller needs, from the auth plugins (or an ``auth`` label)."""
    if "jwt-auth" in plugins or "jwt" in plugins or "openid-connect" in plugins:
        return "Authorization", "Bearer <access token>"
    if "key-auth" in plugins:
        config = plugins["key-auth"] or {}
        header = config.get("header") or (config.get("key_names") or ["apikey"])[0]
        return header, "<API key>"
    if "basic-auth" in plugins:
        return "Authorization", "Basic <credentials>"
    # The gateway may leave token checks to the upstream and say so in a label
    # (oan_grievance_service routes carry auth: bearer).
    if str(labels.get("auth", "")).lower() == "bearer":
        return "Authorization", "Bearer <access token>"
    return None, None


# ------------------------------------------------- APISIX consumers (apps)
# Each sandbox app is one consumer. Credentials use the Admin API's
# ``/consumers/{name}/credentials`` resource (APISIX 3.9+), so an app can
# hold several keys at once and one can be revoked on its own.

#: Label on every consumer the sandbox owns. ADC syncs select their own app
#: labels, so they never touch these consumers.
MANAGED_LABEL = {"managed_by": "oan-sandbox"}


def app_sync_configured() -> bool:
    return bool(
        settings.GATEWAY_APP_SYNC_ENABLED
        and settings.GATEWAY_ADMIN_URL
        and settings.GATEWAY_TYPE == "apisix"
    )


def _admin_client() -> httpx.Client:
    if not app_sync_configured():
        raise ValidationError(
            "App provisioning needs GATEWAY_APP_SYNC_ENABLED, GATEWAY_ADMIN_URL and GATEWAY_TYPE=apisix."
        )
    return httpx.Client(
        base_url=settings.GATEWAY_ADMIN_URL.rstrip("/"),
        timeout=settings.GATEWAY_ADMIN_TIMEOUT,
        headers=_admin_headers(),
    )


def _call(method: str, path: str, json: dict[str, Any] | None = None, missing_ok: bool = False) -> Any:
    try:
        with _admin_client() as client:
            response = client.request(method, path, json=json)
            if missing_ok and response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json() if response.content else None
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:300]
        logger.warning("APISIX %s %s answered %s: %s", method, path, exc.response.status_code, detail)
        raise UpstreamError(
            f"APISIX Admin API answered HTTP {exc.response.status_code} for {method} {path}: {detail}"
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("APISIX Admin API unreachable: %s", exc)
        raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL.") from exc


def list_routes() -> list[GatewayRoute]:
    """Every route with its id, methods and OpenAPI-style paths."""
    try:
        with _admin_client() as client:
            return _read_apisix(client).routes
    except httpx.HTTPError as exc:
        logger.warning("APISIX Admin API unreachable: %s", exc)
        raise UpstreamError("The APISIX Admin API could not be reached at GATEWAY_ADMIN_URL.") from exc


def put_consumer(
    username: str, description: str, labels: dict[str, str], plugins: dict[str, Any]
) -> None:
    _call(
        "PUT",
        "/apisix/admin/consumers",
        {"username": username, "desc": description[:256], "labels": {**MANAGED_LABEL, **labels}, "plugins": plugins},
    )


def delete_consumer(username: str) -> None:
    _call("DELETE", f"/apisix/admin/consumers/{username}", missing_ok=True)


def list_credential_ids(username: str) -> list[str]:
    body = _call("GET", f"/apisix/admin/consumers/{username}/credentials", missing_ok=True) or {}
    return [
        str(entry["value"]["id"])
        for entry in body.get("list") or []
        if (entry.get("value") or {}).get("id")
    ]


def put_credential(username: str, credential_id: str, description: str, plugins: dict[str, Any]) -> None:
    _call(
        "PUT",
        f"/apisix/admin/consumers/{username}/credentials/{credential_id}",
        {"desc": description[:256], "labels": dict(MANAGED_LABEL), "plugins": plugins},
    )


def delete_credential(username: str, credential_id: str) -> None:
    _call("DELETE", f"/apisix/admin/consumers/{username}/credentials/{credential_id}", missing_ok=True)
