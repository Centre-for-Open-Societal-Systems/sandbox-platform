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
"""

from __future__ import annotations

import threading
import time
from typing import Any
from urllib.parse import quote

import httpx

from app.config.settings import settings
from app.core.exceptions import UpstreamError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

_token_lock = threading.Lock()
_token: dict[str, Any] = {"value": None, "expires_at": 0.0}


def is_configured() -> bool:
    return bool(
        settings.PM_PROVISIONING_ENABLED
        and settings.PM_STAFF_API_URL
        and settings.PM_TOKEN_URL
        and settings.PM_CLIENT_ID
        and settings.PM_CLIENT_SECRET
        and settings.PM_PARTNER_JWKS_BASE_URL
    )


def pm_partner_id(partner_id: str) -> str:
    """A partner's PM id, by the Consent Manager's convention: the partner ID it
    presents (``oan-p-42``) upper-cased, ``-`` as ``_``, prefixed ``PARTNER_``."""
    return "PARTNER_" + partner_id.strip().upper().replace("-", "_")


def jwks_url(partner_id: str) -> str:
    return f"{settings.PM_PARTNER_JWKS_BASE_URL.rstrip('/')}/partners/{quote(partner_id)}/jwks.json"


# ------------------------------------------------------------------ partners
def get_partner(pm_id: str) -> dict[str, Any] | None:
    """The PM partner, or None when PM does not know it."""
    return _call("GET", f"/partners/{quote(pm_id)}", missing_ok=True)


def onboard(pm_id: str, partner_id: str, name: str, org_name: str | None,
            description: str, policies: list[dict[str, Any]]) -> dict[str, Any]:
    """Raise the onboarding request; returns it (``id``, ``status``)."""
    return _call("POST", "/partners/requests/onboarding", json={
        "partner_id": pm_id,
        "name": name[:255],
        "org_name": (org_name or "")[:255] or None,
        "description": description,
        "jwks_url": jwks_url(partner_id),
        "keys_from_jwks_url": True,
        "policies": policies,
    })


def open_onboarding_request(pm_id: str) -> dict[str, Any] | None:
    """The partner's onboarding request still waiting for approval, if any."""
    body = _call("GET", "/partners/requests", params={
        "partner_id": pm_id, "status": "created", "request_type": "onboarding",
    }) or {}
    rows = body.get("requests") or []
    return rows[0] if rows else None


def approve(request_id: str, notes: str) -> dict[str, Any]:
    return _call("POST", f"/partners/requests/{quote(request_id)}/approve", json={"notes": notes})


def disable(pm_id: str) -> None:
    _call("POST", f"/partners/{quote(pm_id)}/disable")


def enable(pm_id: str) -> None:
    _call("POST", f"/partners/{quote(pm_id)}/enable")


# ------------------------------------------------------------------ helpers
def _service_token() -> str:
    with _token_lock:
        if _token["value"] and time.monotonic() < _token["expires_at"]:
            return _token["value"]
        try:
            response = httpx.post(
                settings.PM_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.PM_CLIENT_ID,
                    "client_secret": settings.PM_CLIENT_SECRET,
                },
                timeout=settings.PM_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            raise UpstreamError("The token endpoint for Partner Management (PM_TOKEN_URL) could not be reached.") from exc
        if response.status_code != 200:
            logger.warning("PM service-account login answered %s", response.status_code)
            raise UpstreamError(
                f"Keycloak refused the sandbox's Partner Management client ({response.status_code}); "
                "check PM_CLIENT_ID / PM_CLIENT_SECRET."
            )
        body = response.json()
        _token["value"] = body["access_token"]
        _token["expires_at"] = time.monotonic() + max(int(body.get("expires_in", 60)) - 30, 5)
        return _token["value"]


def _call(method: str, path: str, json: Any = None, params: dict[str, Any] | None = None,
          missing_ok: bool = False) -> Any:
    if not is_configured():
        raise ValidationError(
            "Partner Management provisioning needs PM_PROVISIONING_ENABLED, PM_STAFF_API_URL, "
            "PM_TOKEN_URL, PM_CLIENT_ID, PM_CLIENT_SECRET and PM_PARTNER_JWKS_BASE_URL."
        )
    url = f"{settings.PM_STAFF_API_URL.rstrip('/')}{path}"
    try:
        response = httpx.request(
            method, url, json=json, params=params,
            headers={"Authorization": f"Bearer {_service_token()}"},
            timeout=settings.PM_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        raise UpstreamError("Partner Management could not be reached at PM_STAFF_API_URL.") from exc
    if missing_ok and response.status_code == 404:
        return None
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("PM %s %s answered %s: %s", method, path, response.status_code, detail)
        raise UpstreamError(f"Partner Management answered HTTP {response.status_code} for {method} {path}: {detail}")
    return response.json() if response.content else None
