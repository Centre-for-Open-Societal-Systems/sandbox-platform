"""COSS Consent Manager (CM) staff API: a partner's policy bindings.

While COSS keeps data policies in the Consent Manager (``POLICY_BACKEND=cm``), a
partner's access to a registry is a CM **binding** - one per (``audience``,
``controller_id``) - with a versioned policy. Saving a policy that widens access
creates a ``pending`` version that AWE's approvers decide (maker-checker in COSS
itself); a narrowing applies at once. A binding is never deleted: it is
``suspended``. Contract: ``openg2p_contract.CM_*``.

The sandbox signs in with its own service-account client (client-credentials grant
at ``CM_ADMIN_TOKEN_URL``) holding ``CONSENT_MANAGER_ADMIN``. Production's own CM
is reached inside ``with use_target(production_target())`` (``CM_PROD_ADMIN_*``).
"""

from __future__ import annotations

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

UAT = "UAT"
PRODUCTION = "PRODUCTION"
_BASE = "/consent/v1"

_token_lock = threading.Lock()
_tokens: dict[tuple[str, str], dict[str, Any]] = {}


@dataclass(frozen=True, slots=True)
class Target:
    environment: str
    api_url: str
    token_url: str
    client_id: str
    client_secret: str
    prefix: str


def main_target() -> Target:
    return Target(UAT, settings.CM_ADMIN_API_URL, settings.CM_ADMIN_TOKEN_URL, settings.CM_ADMIN_CLIENT_ID,
                  settings.CM_ADMIN_CLIENT_SECRET, "CM_ADMIN")


def production_target() -> Target | None:
    if not settings.CM_PROD_ADMIN_API_URL:
        return None
    return Target(PRODUCTION, settings.CM_PROD_ADMIN_API_URL, settings.CM_PROD_ADMIN_TOKEN_URL,
                  settings.CM_PROD_ADMIN_CLIENT_ID or settings.CM_ADMIN_CLIENT_ID,
                  settings.CM_PROD_ADMIN_CLIENT_SECRET, "CM_PROD_ADMIN")


def is_configured(target: Target | None) -> bool:
    return bool(target and target.api_url and target.token_url and target.client_id and target.client_secret)


_active: ContextVar[Target | None] = ContextVar("cm_target", default=None)


@contextmanager
def use_target(target: Target) -> Iterator[Target]:
    token = _active.set(target)
    try:
        yield target
    finally:
        _active.reset(token)


def current_target() -> Target:
    return _active.get() or main_target()


class PolicyPending(UpstreamError):
    """Another version of the binding's policy already awaits approval (HTTP 409)."""

    def __init__(self, pending_version: int | None):
        super().__init__(f"Policy version {pending_version} is awaiting approval in the Consent Manager.")
        self.pending_version = pending_version


# ----------------------------------------------------------------- bindings
def find_binding(audience: str, controller_id: str) -> dict[str, Any] | None:
    rows = _call("GET", "/partners", params={"audience": audience, "controller_id": controller_id}) or []
    return next((r for r in rows if r.get("audience") == audience and r.get("controller_id") == controller_id), None)


def create_binding(audience: str, controller_id: str, partner_mgmt_id: str | None, name: str) -> dict[str, Any]:
    return _call("POST", "/partners", json={
        "audience": audience, "controller_id": controller_id,
        "partner_mgmt_id": partner_mgmt_id, "name": name[:255],
    })


def set_binding_status(binding_id: str, status: str) -> dict[str, Any]:
    """``active`` / ``suspended`` (a binding is never deleted)."""
    return _call("PATCH", f"/partners/{quote(binding_id)}", json={"status": status})


def upsert_policy(binding_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Save a new policy version; its ``status``: active (applied), pending (a widening
    AWE's approvers decide) or failed (not submitted to AWE). Raises PolicyPending when
    another version already waits."""
    return _call("PUT", f"/partners/{quote(binding_id)}/policy", json=fields, conflict=True)


def list_policies(binding_id: str) -> list[dict[str, Any]]:
    return _call("GET", f"/partners/{quote(binding_id)}/policies", missing_ok=True) or []


def meta() -> dict[str, Any]:
    """Known controller ids, data scopes, purposes ... (``GET /consent/v1/meta``)."""
    return _call("GET", "/meta") or {}


# ------------------------------------------------------------------ helpers
def _service_token(target: Target) -> str:
    cached = _tokens.setdefault((target.token_url, target.client_id), {"value": None, "expires_at": 0.0})
    with _token_lock:
        if cached["value"] and time.monotonic() < cached["expires_at"]:
            return cached["value"]
        try:
            response = httpx.post(target.token_url, data={
                "grant_type": "client_credentials", "client_id": target.client_id,
                "client_secret": target.client_secret,
            }, timeout=settings.PM_TIMEOUT)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"{target.prefix}_TOKEN_URL could not be reached.") from exc
        if response.status_code != 200:
            raise UpstreamError(
                f"Keycloak refused the sandbox's Consent Manager client ({response.status_code}); "
                f"check {target.prefix}_CLIENT_ID / {target.prefix}_CLIENT_SECRET."
            )
        body = response.json()
        cached["value"] = body["access_token"]
        cached["expires_at"] = time.monotonic() + max(int(body.get("expires_in", 60)) - 30, 5)
        return cached["value"]


def _call(method: str, path: str, json: Any = None, params: dict[str, Any] | None = None,
          missing_ok: bool = False, conflict: bool = False) -> Any:
    target = current_target()
    if not is_configured(target):
        p = target.prefix
        raise ValidationError(f"The Consent Manager staff API needs {p}_API_URL, {p}_TOKEN_URL, {p}_CLIENT_ID "
                              f"and {p}_CLIENT_SECRET.")
    url = f"{target.api_url.rstrip('/')}{_BASE}{path}"
    try:
        response = httpx.request(method, url, json=json, params=params, timeout=settings.PM_TIMEOUT,
                                 headers={"Authorization": f"Bearer {_service_token(target)}"})
    except httpx.HTTPError as exc:
        raise UpstreamError(f"The Consent Manager could not be reached at {target.prefix}_API_URL.") from exc
    if missing_ok and response.status_code == 404:
        return None
    if conflict and response.status_code == 409:
        body = response.json() if response.content else {}
        if body.get("error") == "policy_pending":
            raise PolicyPending(body.get("pending_version"))
    if response.status_code >= 400:
        detail = response.text[:300]
        logger.warning("CM %s %s answered %s: %s", method, path, response.status_code, detail)
        raise UpstreamError(f"The Consent Manager answered HTTP {response.status_code} for {method} {path}: {detail}")
    return response.json() if response.content else None
