"""Keycloak Admin REST API: participant users in the partners realm.

Every participant is one Keycloak **user** (username = their email). What
they may do is a **client role** of one shared client
(``KEYCLOAK_PARTNER_CLIENT_ID``, e.g. ``oan-partner-api``): ``uat``,
``production``. Users scale to any number of participants; a client
per participant would not.

The sandbox authenticates as its own service-account client
(``KEYCLOAK_ADMIN_CLIENT_ID``, client-credentials grant) with only the
realm-management roles it needs (manage-users, view-users, query-users,
view-clients, query-clients) - never as the Keycloak admin user. The token is
cached until shortly before it expires.

Realm, shared client, roles and token claims are set up once by
``scripts/keycloak/setup_partner_realm.py``.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.config.settings import settings
from app.core.exceptions import UpstreamError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

_token_lock = threading.Lock()
_token: dict[str, Any] = {"value": None, "expires_at": 0.0}
# Keycloak's internal id of the shared partner client (looked up once).
_partner_client: dict[str, str] = {}

#: Client roles of the shared client, one per environment.
ENVIRONMENT_ROLES = ("uat", "production")
#: Roles of environments that no longer exist: taken away at the next sync.
RETIRED_ROLES = ("sandbox",)


def is_configured() -> bool:
    return bool(
        settings.KEYCLOAK_PROVISIONING_ENABLED
        and settings.KEYCLOAK_URL
        and settings.KEYCLOAK_REALM
        and settings.KEYCLOAK_ADMIN_CLIENT_ID
        and settings.KEYCLOAK_ADMIN_CLIENT_SECRET
        and settings.KEYCLOAK_PARTNER_CLIENT_ID
    )


def token_url(public: bool = True) -> str:
    base = (settings.KEYCLOAK_PUBLIC_URL if public else "") or settings.KEYCLOAK_URL
    return f"{base.rstrip('/')}/realms/{quote(settings.KEYCLOAK_REALM)}/protocol/openid-connect/token"


def console_url(user_id: str) -> str:
    """The user's page in the Keycloak admin console (for administrators)."""
    base = (settings.KEYCLOAK_PUBLIC_URL or settings.KEYCLOAK_URL).rstrip("/")
    return f"{base}/admin/master/console/#/{quote(settings.KEYCLOAK_REALM)}/users/{user_id}/settings"


# -------------------------------------------------------------------- users
def find_user(username: str) -> str | None:
    """Keycloak id of the user with exactly this username, or None."""
    rows = _call("GET", "/users", params={"username": username, "exact": "true", "briefRepresentation": "true"}) or []
    for row in rows:
        if row.get("username", "").lower() == username.lower():
            return row["id"]
    return None


def create_user(
    username: str,
    email: str,
    first_name: str,
    last_name: str,
    *,
    enabled: bool,
    email_verified: bool,
    attributes: dict[str, str],
    password: str | None = None,
) -> str:
    """Create the user (with a password when given) and return its id."""
    body: dict[str, Any] = {
        "username": username,
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": enabled,
        "emailVerified": email_verified,
        "attributes": {name: [value] for name, value in attributes.items()},
        "requiredActions": [],
    }
    if password:
        body["credentials"] = [{"type": "password", "value": password, "temporary": False}]
    _call("POST", "/users", json=body)
    user_id = find_user(username)
    if user_id is None:
        raise UpstreamError(f"Keycloak did not return the new user '{username}'.")
    return user_id


def update_user(
    user_id: str,
    *,
    email: str,
    first_name: str,
    last_name: str,
    enabled: bool,
    email_verified: bool,
    attributes: dict[str, str],
) -> None:
    user = _call("GET", f"/users/{user_id}")
    user.update(
        email=email,
        firstName=first_name,
        lastName=last_name,
        enabled=enabled,
        emailVerified=email_verified,
        attributes={**(user.get("attributes") or {}), **{name: [value] for name, value in attributes.items()}},
    )
    _call("PUT", f"/users/{user_id}", json=user)


def set_password(user_id: str, password: str) -> None:
    _call("PUT", f"/users/{user_id}/reset-password", json={"type": "password", "value": password, "temporary": False})


def set_environment_roles(user_id: str, roles: set[str]) -> None:
    """Give the user exactly these environment roles of the shared client."""
    _set_client_roles(
        user_id, settings.KEYCLOAK_PARTNER_CLIENT_ID, roles, ENVIRONMENT_ROLES + RETIRED_ROLES
    )


def logout_user(user_id: str) -> None:
    """End every Keycloak session of the user (their refresh tokens stop working)."""
    _call("POST", f"/users/{user_id}/logout")


def delete_session(sid: str) -> None:
    """End one Keycloak session (sign-out); an already ended one is fine."""
    _call("DELETE", f"/sessions/{quote(sid)}", missing_ok=True)


def set_portal_role(user_id: str, granted: bool) -> None:
    """Give or take the Consent Manager partner portal role (KEYCLOAK_PORTAL_ROLE)."""
    role = settings.KEYCLOAK_PORTAL_ROLE
    _set_client_roles(
        user_id, settings.KEYCLOAK_PORTAL_CLIENT_ID, {role} if granted else set(), (role,)
    )


# ------------------------------------------------------------------ helpers
def _set_client_roles(user_id: str, client_id: str, roles: set[str], managed: tuple[str, ...]) -> None:
    """The user holds exactly ``roles`` among ``managed`` roles of ``client_id``;
    its other roles of that client are left alone."""
    client = _client_uuid(client_id)
    path = f"/users/{user_id}/role-mappings/clients/{client}"
    current = {r["name"]: r for r in (_call("GET", path) or []) if r["name"] in managed}
    extra = [current[name] for name in current if name not in roles]
    missing = [_client_role(client, client_id, name) for name in sorted(roles) if name not in current]
    if extra:
        _call("DELETE", path, json=extra)
    if missing:
        _call("POST", path, json=missing)


# ------------------------------------------------- app clients (GATEWAY_PARTNER_AUTH=oauth)
#: Client attribute marking the clients the sandbox owns (value: the app's unique id);
#: only clients carrying it are ever changed or deleted.
APP_CLIENT_ATTRIBUTE = "oan.sandbox.app"


def _find_client(client_id: str) -> dict[str, Any] | None:
    rows = _call("GET", "/clients", params={"clientId": client_id, "search": "false"}) or []
    return next((row for row in rows if row.get("clientId") == client_id), None)


def upsert_app_client(
    client_id: str, secret: str, app_uid: str, description: str, claims: dict[str, Any]
) -> None:
    """One app key as an OAuth confidential client (client credentials only) whose access
    tokens carry ``claims`` (hard-coded claim mappers: strings, or lists as JSON)."""
    body = {
        "clientId": client_id,
        "name": description[:255],
        "description": description[:255],
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "clientAuthenticatorType": "client-secret",
        "secret": secret,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "frontchannelLogout": False,
        "redirectUris": [],
        "webOrigins": [],
        # Only the claims below: no realm or other clients' roles in its tokens.
        "fullScopeAllowed": False,
        "attributes": {"access.token.lifespan": "300", APP_CLIENT_ATTRIBUTE: app_uid},
    }
    found = _find_client(client_id)
    if found is None:
        _call("POST", "/clients", json=body)
        found = _find_client(client_id)
        if found is None:
            raise UpstreamError(f"Keycloak did not create client '{client_id}'.")
    else:
        if (found.get("attributes") or {}).get(APP_CLIENT_ATTRIBUTE) is None:
            raise UpstreamError(f"Keycloak client '{client_id}' exists and is not the sandbox's.")
        _call("PUT", f"/clients/{found['id']}", json={**found, **body,
                                                      "attributes": {**(found.get("attributes") or {}),
                                                                     **body["attributes"]}})
    uuid = found["id"]
    existing = {m["name"]: m for m in _call("GET", f"/clients/{uuid}/protocol-mappers/models") or []}
    for name, value in claims.items():
        is_list = isinstance(value, list | tuple)
        mapper = {
            "name": name,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-hardcoded-claim-mapper",
            "config": {
                "claim.name": name,
                "claim.value": json.dumps(list(value)) if is_list else str(value),
                "jsonType.label": "JSON" if is_list else "String",
                "access.token.claim": "true",
                "id.token.claim": "false",
                "userinfo.token.claim": "false",
                "introspection.token.claim": "true",
            },
        }
        if name in existing:
            current = existing[name]
            if current.get("config") != mapper["config"]:
                _call("PUT", f"/clients/{uuid}/protocol-mappers/models/{current['id']}",
                      json={**mapper, "id": current["id"]})
        else:
            _call("POST", f"/clients/{uuid}/protocol-mappers/models", json=mapper)


def delete_app_client(client_id: str) -> None:
    """Remove an app key's client; clients the sandbox does not own are never touched."""
    found = _find_client(client_id)
    if found and (found.get("attributes") or {}).get(APP_CLIENT_ATTRIBUTE) is not None:
        _call("DELETE", f"/clients/{found['id']}", missing_ok=True)


def request_app_token(client_id: str, secret: str) -> dict[str, Any]:
    """Keycloak's token response for an app key: client credentials (API key + secret).

    A new token every time, the request a partner makes itself (no cache), so the
    portal's "Get token" shows what the partner gets.
    """
    try:
        response = httpx.post(
            token_url(public=False),
            data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret},
            timeout=settings.KEYCLOAK_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Keycloak could not be reached at KEYCLOAK_URL.") from exc
    if response.status_code != 200:
        raise UpstreamError(
            f"Keycloak refused the app's key ({response.status_code}); its client may not be synced yet."
        )
    return response.json()


def unverified_claims(token: str) -> dict[str, Any]:
    """A token's claims, for display only: the gateway verifies the token, not this."""
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return {}


def _client_uuid(client_id: str) -> str:
    if client_id not in _partner_client:
        rows = _call("GET", "/clients", params={"clientId": client_id, "search": "false"}) or []
        match = next((row for row in rows if row.get("clientId") == client_id), None)
        if match is None:
            raise UpstreamError(
                f"Keycloak has no client '{client_id}' in realm '{settings.KEYCLOAK_REALM}'; "
                "run scripts/keycloak/setup_partner_realm.py."
            )
        _partner_client[client_id] = match["id"]
    return _partner_client[client_id]


def _client_role(client: str, client_id: str, name: str) -> dict[str, Any]:
    role = _call("GET", f"/clients/{client}/roles/{quote(name)}", missing_ok=True)
    if role is None:
        raise UpstreamError(
            f"Client '{client_id}' has no role '{name}'; "
            "run scripts/keycloak/setup_partner_realm.py."
        )
    return role


def _admin_token() -> str:
    with _token_lock:
        if _token["value"] and time.monotonic() < _token["expires_at"]:
            return _token["value"]
        try:
            response = httpx.post(
                token_url(public=False),
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.KEYCLOAK_ADMIN_CLIENT_ID,
                    "client_secret": settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
                },
                timeout=settings.KEYCLOAK_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("Keycloak could not be reached at KEYCLOAK_URL.") from exc
        if response.status_code != 200:
            logger.warning("Keycloak service-account login answered %s", response.status_code)
            raise UpstreamError(
                f"Keycloak refused the sandbox's service account ({response.status_code}); "
                "check KEYCLOAK_ADMIN_CLIENT_ID / KEYCLOAK_ADMIN_CLIENT_SECRET."
            )
        body = response.json()
        _token["value"] = body["access_token"]
        # Renew 30 s early so a call never starts with an expiring token.
        _token["expires_at"] = time.monotonic() + max(int(body.get("expires_in", 60)) - 30, 5)
        return _token["value"]


def _call(
    method: str,
    path: str,
    json: Any = None,
    params: dict[str, Any] | None = None,
    missing_ok: bool = False,
) -> Any:
    if not is_configured():
        raise ValidationError(
            "Keycloak provisioning needs KEYCLOAK_PROVISIONING_ENABLED, KEYCLOAK_URL, KEYCLOAK_REALM, "
            "KEYCLOAK_PARTNER_CLIENT_ID and the KEYCLOAK_ADMIN_CLIENT_* service account."
        )
    url = f"{settings.KEYCLOAK_URL.rstrip('/')}/admin/realms/{quote(settings.KEYCLOAK_REALM)}{path}"
    try:
        response = httpx.request(
            method,
            url,
            json=json,
            params=params,
            headers={"Authorization": f"Bearer {_admin_token()}"},
            timeout=settings.KEYCLOAK_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Keycloak could not be reached at KEYCLOAK_URL.") from exc
    if missing_ok and response.status_code == 404:
        return None
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("Keycloak %s %s answered %s: %s", method, path, response.status_code, detail)
        raise UpstreamError(f"Keycloak answered HTTP {response.status_code} for {method} {path}: {detail}")
    return response.json() if response.content else None
