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

Production may run its own Keycloak (``KEYCLOAK_PROD_URL``). App clients of
production (GATEWAY_PARTNER_AUTH=oauth) are then written there: every call in
a ``with use_realm(realm_for("PRODUCTION"))`` block goes to that realm, with
its own service account. Outside such a block, and whenever
``KEYCLOAK_PROD_URL`` is empty, everything goes to the main Keycloak
(``KEYCLOAK_URL``), as before. Participant users always stay on the main one.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.config.settings import settings
from app.core.exceptions import UpstreamError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

_token_lock = threading.Lock()
# Service-account tokens, one per realm: (url, realm, client id) -> value, expiry.
_tokens: dict[tuple[str, str, str], dict[str, Any]] = {}
# Keycloak's internal id of the shared partner client (looked up once).
_partner_client: dict[str, str] = {}

#: Client roles of the shared client, one per environment.
ENVIRONMENT_ROLES = ("uat", "production")
#: Roles of environments that no longer exist: taken away at the next sync.
RETIRED_ROLES = ("sandbox",)

PRODUCTION = "PRODUCTION"


@dataclass(frozen=True, slots=True)
class Realm:
    """A Keycloak realm the sandbox writes app clients to."""

    #: "UAT" for the main Keycloak, "PRODUCTION" for production's own.
    environment: str
    url: str
    public_url: str
    name: str
    admin_client_id: str
    admin_client_secret: str
    certs_url: str
    #: The setting named in error messages.
    url_setting: str


def main_realm() -> Realm:
    """The main Keycloak (KEYCLOAK_*): participant users, UAT, and production unless it has its own."""
    return Realm(
        environment="UAT",
        url=settings.KEYCLOAK_URL,
        public_url=settings.KEYCLOAK_PUBLIC_URL,
        name=settings.KEYCLOAK_REALM,
        admin_client_id=settings.KEYCLOAK_ADMIN_CLIENT_ID,
        admin_client_secret=settings.KEYCLOAK_ADMIN_CLIENT_SECRET,
        certs_url=settings.keycloak_certs_url,
        url_setting="KEYCLOAK_URL",
    )


def production_realm() -> Realm | None:
    """Production's own Keycloak (KEYCLOAK_PROD_*), or None when production uses the main one."""
    if not settings.KEYCLOAK_PROD_URL:
        return None
    url = settings.KEYCLOAK_PROD_URL
    name = settings.KEYCLOAK_PROD_REALM or settings.KEYCLOAK_REALM
    return Realm(
        environment=PRODUCTION,
        url=url,
        public_url=settings.KEYCLOAK_PROD_PUBLIC_URL,
        name=name,
        admin_client_id=settings.KEYCLOAK_PROD_ADMIN_CLIENT_ID or settings.KEYCLOAK_ADMIN_CLIENT_ID,
        admin_client_secret=settings.KEYCLOAK_PROD_ADMIN_CLIENT_SECRET,
        certs_url=settings.KEYCLOAK_PROD_JWKS_URL
        or f"{url.rstrip('/')}/realms/{name}/protocol/openid-connect/certs",
        url_setting="KEYCLOAK_PROD_URL",
    )


def separate_production() -> bool:
    return production_realm() is not None


def realm_for(environment: str) -> Realm:
    """The realm holding ``environment``'s app clients."""
    if str(environment).upper() == PRODUCTION:
        return production_realm() or main_realm()
    return main_realm()


_active: ContextVar[Realm | None] = ContextVar("keycloak_realm", default=None)


@contextmanager
def use_realm(realm: Realm) -> Iterator[Realm]:
    """Send the Keycloak calls made inside the block to ``realm``."""
    token = _active.set(realm)
    try:
        yield realm
    finally:
        _active.reset(token)


def current_realm() -> Realm:
    return _active.get() or main_realm()


def is_configured() -> bool:
    return bool(
        settings.KEYCLOAK_PROVISIONING_ENABLED
        and settings.KEYCLOAK_URL
        and settings.KEYCLOAK_REALM
        and settings.KEYCLOAK_ADMIN_CLIENT_ID
        and settings.KEYCLOAK_ADMIN_CLIENT_SECRET
        and settings.KEYCLOAK_PARTNER_CLIENT_ID
    )


def _realm_configured(realm: Realm) -> bool:
    if realm.url_setting == "KEYCLOAK_URL":
        return is_configured()
    return bool(
        settings.KEYCLOAK_PROVISIONING_ENABLED
        and realm.url
        and realm.name
        and realm.admin_client_id
        and realm.admin_client_secret
    )


def token_url(public: bool = True) -> str:
    realm = current_realm()
    base = (realm.public_url if public else "") or realm.url
    return f"{base.rstrip('/')}/realms/{quote(realm.name)}/protocol/openid-connect/token"


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
        raise UpstreamError(f"Keycloak could not be reached at {current_realm().url_setting}.") from exc
    if response.status_code != 200:
        raise UpstreamError(
            f"Keycloak refused the app's key ({response.status_code}); its client may not be synced yet."
        )
    return response.json()


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
    realm = current_realm()
    cached = _tokens.setdefault((realm.url, realm.name, realm.admin_client_id), {"value": None, "expires_at": 0.0})
    prefix = "KEYCLOAK_PROD_ADMIN_CLIENT" if realm.url_setting == "KEYCLOAK_PROD_URL" else "KEYCLOAK_ADMIN_CLIENT"
    with _token_lock:
        if cached["value"] and time.monotonic() < cached["expires_at"]:
            return cached["value"]
        try:
            response = httpx.post(
                token_url(public=False),
                data={
                    "grant_type": "client_credentials",
                    "client_id": realm.admin_client_id,
                    "client_secret": realm.admin_client_secret,
                },
                timeout=settings.KEYCLOAK_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(f"Keycloak could not be reached at {realm.url_setting}.") from exc
        if response.status_code != 200:
            logger.warning("Keycloak service-account login answered %s", response.status_code)
            raise UpstreamError(
                f"Keycloak refused the sandbox's service account ({response.status_code}); "
                f"check {prefix}_ID / {prefix}_SECRET."
            )
        body = response.json()
        cached["value"] = body["access_token"]
        # Renew 30 s early so a call never starts with an expiring token.
        cached["expires_at"] = time.monotonic() + max(int(body.get("expires_in", 60)) - 30, 5)
        return cached["value"]


def _call(
    method: str,
    path: str,
    json: Any = None,
    params: dict[str, Any] | None = None,
    missing_ok: bool = False,
) -> Any:
    realm = current_realm()
    if not _realm_configured(realm):
        if realm.url_setting == "KEYCLOAK_PROD_URL":
            raise ValidationError(
                "Production's Keycloak needs KEYCLOAK_PROVISIONING_ENABLED, KEYCLOAK_PROD_URL and the "
                "KEYCLOAK_PROD_ADMIN_CLIENT_* service account."
            )
        raise ValidationError(
            "Keycloak provisioning needs KEYCLOAK_PROVISIONING_ENABLED, KEYCLOAK_URL, KEYCLOAK_REALM, "
            "KEYCLOAK_PARTNER_CLIENT_ID and the KEYCLOAK_ADMIN_CLIENT_* service account."
        )
    url = f"{realm.url.rstrip('/')}/admin/realms/{quote(realm.name)}{path}"
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
        raise UpstreamError(f"Keycloak could not be reached at {realm.url_setting}.") from exc
    if missing_ok and response.status_code == 404:
        return None
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("Keycloak %s %s answered %s: %s", method, path, response.status_code, detail)
        raise UpstreamError(f"Keycloak answered HTTP {response.status_code} for {method} {path}: {detail}")
    return response.json() if response.content else None
