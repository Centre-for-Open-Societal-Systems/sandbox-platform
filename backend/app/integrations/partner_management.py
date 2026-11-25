"""OpenG2P Partner Management (PM) staff API: participants as PM partners.

The Consent Manager's partner portal reads what a partner may do (its access
policies) from PM, so an approved participant must be a PM partner too. The
sandbox raises PM's onboarding request and approves it itself, then disables /
enables the partner as the participant's access changes.

PM requires a public key or a JWKS URL to onboard. The sandbox gives the JWKS
URL it serves for the partner (``/partners/{partner_id}/jwks.json``) and asks
PM to read the keys from it when needed (``keys_from_jwks_url``), so a
participant without a key can still be onboarded.

The sandbox signs in with its own service-account client (client-credentials
grant at ``PM_TOKEN_URL``) holding PM's admin role. The token is cached until
shortly before it expires.

Production runs its own PM (``PM_PROD_*``, one per cluster): calls made inside a
``with use_target(production_target())`` block go there, with production's own
service account, JWKS URL (``/partners/{id}/production/jwks.json``: only while the
participant has production access) and default policies. Whether the sandbox also
approves its onboarding request is per PM (``PM_AUTO_APPROVE``,
``PM_PROD_AUTO_APPROVE``): off, the request waits for PM's own staff
(maker-checker) and the sandbox only reads the outcome.
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
from app.integrations import openg2p_contract

logger = get_logger(__name__)

_token_lock = threading.Lock()
# Service-account tokens per PM: (token URL, client id) -> value, expiry.
_tokens: dict[tuple[str, str], dict[str, Any]] = {}

UAT = "UAT"
PRODUCTION = "PRODUCTION"


@dataclass(frozen=True, slots=True)
class Target:
    """One Partner Management (its staff API and the sandbox's account there)."""

    environment: str
    staff_api_url: str
    token_url: str
    client_id: str
    client_secret: str
    jwks_base_url: str
    #: The sandbox approves its own onboarding requests (else PM staff do).
    auto_approve: bool
    #: PolicyInput objects given at onboarding (JSON list).
    policies: str
    #: Setting prefix named in error messages.
    prefix: str
    #: PM release (openg2p_contract.PM_PROFILES) or "auto".
    api_version: str = "auto"


def main_target() -> Target:
    return Target(UAT, settings.PM_STAFF_API_URL, settings.PM_TOKEN_URL, settings.PM_CLIENT_ID,
                  settings.PM_CLIENT_SECRET, settings.PM_PARTNER_JWKS_BASE_URL, settings.PM_AUTO_APPROVE,
                  settings.PM_DEFAULT_POLICIES, "PM", settings.PM_API_VERSION)


def production_target() -> Target | None:
    """Production's own PM (PM_PROD_*), or None when there is none."""
    if not settings.PM_PROD_STAFF_API_URL:
        return None
    return Target(
        PRODUCTION,
        settings.PM_PROD_STAFF_API_URL,
        settings.PM_PROD_TOKEN_URL,
        settings.PM_PROD_CLIENT_ID or settings.PM_CLIENT_ID,
        settings.PM_PROD_CLIENT_SECRET,
        settings.PM_PROD_PARTNER_JWKS_BASE_URL or settings.PM_PARTNER_JWKS_BASE_URL,
        settings.PM_PROD_AUTO_APPROVE,
        settings.PM_PROD_DEFAULT_POLICIES,
        "PM_PROD",
        settings.PM_PROD_API_VERSION,
    )


_active: ContextVar[Target | None] = ContextVar("pm_target", default=None)


@contextmanager
def use_target(target: Target) -> Iterator[Target]:
    """Send the PM calls made inside the block to ``target``."""
    token = _active.set(target)
    try:
        yield target
    finally:
        _active.reset(token)


def current_target() -> Target:
    return _active.get() or main_target()


def default_policies() -> list[dict[str, Any]]:
    return json.loads(current_target().policies or "[]")


# Detected releases per staff API URL ("auto"), kept for the life of the process.
_detected: dict[str, str] = {}


def profile(target: Target | None = None) -> openg2p_contract.PmProfile:
    """What the PM offers (openg2p_contract.PM_PROFILES). ``auto``: GET /metadata exists
    on develop only, so a 404 means 1.0. Raises when PM cannot be reached to tell."""
    target = target or current_target()
    if target.api_version != "auto":
        return openg2p_contract.pm_profile(target.api_version)
    if target.staff_api_url not in _detected:
        with use_target(target):
            found = _call("GET", "/metadata", missing_ok=True)
        _detected[target.staff_api_url] = "1.0" if found is None else "develop"
        logger.info("Partner Management at %s_STAFF_API_URL is release %s",
                    target.prefix, _detected[target.staff_api_url])
    return openg2p_contract.pm_profile(_detected[target.staff_api_url])


def is_configured(target: Target | None = None) -> bool:
    target = target or current_target()
    return bool(
        settings.PM_PROVISIONING_ENABLED
        and target.staff_api_url
        and target.token_url
        and target.client_id
        and target.client_secret
        and target.jwks_base_url
    )


def pm_partner_id(partner_id: str) -> str:
    """A partner's PM id, by the Consent Manager's convention: the partner ID it
    presents (``oan-p-42``) upper-cased, ``-`` as ``_``, prefixed ``PARTNER_``."""
    return "PARTNER_" + partner_id.strip().upper().replace("-", "_")


def jwks_url(partner_id: str) -> str:
    """Where the current PM reads the partner's keys: production's has its own path, served
    only while the participant has production access."""
    target = current_target()
    env = "production/" if target.environment == PRODUCTION else ""
    return f"{target.jwks_base_url.rstrip('/')}/partners/{quote(partner_id)}/{env}jwks.json"


# ------------------------------------------------------------------ partners
def get_partner(pm_id: str) -> dict[str, Any] | None:
    """The PM partner, or None when PM does not know it."""
    return _call("GET", f"/partners/{quote(pm_id)}", missing_ok=True)


def onboard(pm_id: str, partner_id: str, name: str, org_name: str | None,
            description: str, policies: list[dict[str, Any]]) -> dict[str, Any]:
    """Raise the onboarding request; returns it (``id``, ``status``).

    A PM with live JWKS reads the keys from the sandbox when it needs them; an older one
    (1.0) copies them once from the same URL (``import_from_jwks_url``), so the partner
    must have a key by then. Policies go only to a PM that has them."""
    caps = profile()
    body: dict[str, Any] = {
        "partner_id": pm_id,
        "name": name[:255],
        "org_name": (org_name or "")[:255] or None,
        "description": description,
        "jwks_url": jwks_url(partner_id),
    }
    if caps.live_jwks:
        body["keys_from_jwks_url"] = True
    else:
        body["import_from_jwks_url"] = True
    if caps.policies and policies:
        body["policies"] = policies
    return _call("POST", "/partners/requests/onboarding", json=body)


def active_kids(pm_id: str) -> set[str]:
    """kids of the partner's keys PM serves (status active)."""
    rows = _call("GET", f"/partners/{quote(pm_id)}/keys") or []
    return {row["kid"] for row in rows if row.get("status") == "active" and row.get("kid")}


def key_update(pm_id: str, partner_id: str, description: str, revoke_kids: list[str]) -> dict[str, Any]:
    """File a key-update request: the keys now in the sandbox's JWKS are added (copied
    from it) and ``revoke_kids`` revoked, when it is approved."""
    return _call("POST", "/partners/requests/key-update", json={
        "partner_id": pm_id,
        "description": description[:2000],
        "jwks_url": jwks_url(partner_id),
        "import_from_jwks_url": True,
        "revoke_kids": revoke_kids,
    })


def open_request(pm_id: str, request_type: str) -> dict[str, Any] | None:
    """The partner's request of that type still waiting for a decision, if any."""
    body = _call("GET", "/partners/requests", params={
        "partner_id": pm_id, "status": "created", "request_type": request_type,
    }) or {}
    rows = body.get("requests") or []
    return rows[0] if rows else None


def open_onboarding_request(pm_id: str) -> dict[str, Any] | None:
    """The partner's onboarding request still waiting for approval, if any."""
    body = _call("GET", "/partners/requests", params={
        "partner_id": pm_id, "status": "created", "request_type": "onboarding",
    }) or {}
    rows = body.get("requests") or []
    return rows[0] if rows else None


def approve(request_id: str, notes: str) -> dict[str, Any]:
    return _call("POST", f"/partners/requests/{quote(request_id)}/approve", json={"notes": notes})


def request_policies(pm_id: str, description: str, policies: list[dict[str, Any]],
                     revoke: list[dict[str, str]]) -> dict[str, Any]:
    """File a policy request: new versions of ``policies`` and revocation of ``revoke``
    (``{"data_controller": X}`` / ``{"use_case": Y}``), applied when it is approved."""
    return _call("POST", "/partners/requests/policy", json={
        "partner_id": pm_id, "description": description[:2000], "policies": policies, "revoke": revoke,
    })


def get_request(request_id: str) -> dict[str, Any] | None:
    """A partner request (``status``: created / approved / rejected)."""
    return _call("GET", f"/partners/requests/{quote(request_id)}", missing_ok=True)


def catalogue() -> list[dict[str, Any]]:
    """The policy choices PM offers (registries' data scopes, use cases, purposes...)."""
    return (_call("GET", "/catalogue") or {}).get("sources") or []


def disable(pm_id: str) -> None:
    _call("POST", f"/partners/{quote(pm_id)}/disable")


def enable(pm_id: str) -> None:
    _call("POST", f"/partners/{quote(pm_id)}/enable")


# ------------------------------------------------------------------ helpers
def _service_token() -> str:
    target = current_target()
    cached = _tokens.setdefault((target.token_url, target.client_id), {"value": None, "expires_at": 0.0})
    with _token_lock:
        if cached["value"] and time.monotonic() < cached["expires_at"]:
            return cached["value"]
        try:
            response = httpx.post(
                target.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": target.client_id,
                    "client_secret": target.client_secret,
                },
                timeout=settings.PM_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError(
                f"The token endpoint for Partner Management ({target.prefix}_TOKEN_URL) could not be reached."
            ) from exc
        if response.status_code != 200:
            logger.warning("PM service-account login answered %s", response.status_code)
            raise UpstreamError(
                f"Keycloak refused the sandbox's Partner Management client ({response.status_code}); "
                f"check {target.prefix}_CLIENT_ID / {target.prefix}_CLIENT_SECRET."
            )
        body = response.json()
        cached["value"] = body["access_token"]
        cached["expires_at"] = time.monotonic() + max(int(body.get("expires_in", 60)) - 30, 5)
        return cached["value"]


def _call(method: str, path: str, json: Any = None, params: dict[str, Any] | None = None,
          missing_ok: bool = False) -> Any:
    target = current_target()
    if not is_configured(target):
        p = target.prefix
        raise ValidationError(
            f"Partner Management provisioning needs PM_PROVISIONING_ENABLED, {p}_STAFF_API_URL, "
            f"{p}_TOKEN_URL, {p}_CLIENT_ID, {p}_CLIENT_SECRET and {p}_PARTNER_JWKS_BASE_URL."
        )
    url = f"{target.staff_api_url.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method, url, json=json, params=params,
            headers={"Authorization": f"Bearer {_service_token()}"},
            timeout=settings.PM_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError(f"Partner Management could not be reached at {target.prefix}_STAFF_API_URL.") from exc
    if missing_ok and response.status_code == 404:
        return None
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("PM %s %s answered %s: %s", method, path, response.status_code, detail)
        raise UpstreamError(f"Partner Management answered HTTP {response.status_code} for {method} {path}: {detail}")
    return response.json() if response.content else None
