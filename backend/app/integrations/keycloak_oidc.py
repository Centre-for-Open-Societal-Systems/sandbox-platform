"""Participant sign-in with Keycloak: tokens from the realm, verified here.

The portal keeps its own sign-in form. The API exchanges the participant's
email and password for Keycloak tokens (direct grant on the confidential
client ``KEYCLOAK_LOGIN_CLIENT_ID``, so the client secret never reaches a
browser), refreshes them with Keycloak's refresh grant and ends the Keycloak
session at sign-out.

Every access token is verified locally, without a call to Keycloak:

    signature (RS256 pinned, key by ``kid`` from the realm's JWKS, cached)
      -> iss -> exp / nbf / iat (with a small leeway) -> typ == Bearer
      -> azp == the login client -> jti and sid present

The algorithm is pinned instead of read from the token header, so a token
signed with HMAC over the published public key (algorithm confusion) or with
``alg: none`` never passes.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
import jwt

from app.config.settings import settings
from app.core.exceptions import (
    AppError,
    ForbiddenError,
    UnauthorizedError,
    UpstreamError,
)
from app.core.logging import get_logger
from app.integrations import keycloak

logger = get_logger(__name__)

#: The only signature algorithm accepted (Keycloak's default realm key).
ALGORITHMS = ["RS256"]

INVALID_CREDENTIALS = "Invalid email or password."
SESSION_INVALID = "Session is expired or invalid."

_jwks_lock = threading.Lock()
_jwks: dict[str, Any] = {"client": None, "url": None}


@dataclass(slots=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int
    refresh_expires_in: int
    claims: dict[str, Any]


class InvalidCredentials(UnauthorizedError):
    """Keycloak refused the email / password (unknown user or wrong password)."""


# ----------------------------------------------------------------- grants
def password_grant(username: str, password: str) -> Tokens:
    """Keycloak checks the password and issues the tokens (direct grant)."""
    return _token_request({"grant_type": "password", "username": username, "password": password,
                           "scope": "openid"})


def refresh_grant(refresh_token: str) -> Tokens:
    """New tokens for a live Keycloak session (the refresh token may be rotated)."""
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})


def end_session(sid: str | None) -> None:
    """End the Keycloak session (best effort: the sandbox session is ended anyway)."""
    if not sid:
        return
    try:
        keycloak.delete_session(sid)
    except AppError as exc:
        logger.warning("Keycloak session %s could not be ended: %s", sid, exc.message)


def revoke_refresh_token(refresh_token: str) -> None:
    """Revoke one refresh token (and its session) at Keycloak; best effort."""
    try:
        httpx.post(
            _endpoint("revoke"),
            data={"token": refresh_token, "token_type_hint": "refresh_token", **_client_auth()},
            timeout=settings.KEYCLOAK_TIMEOUT,
        )
    except httpx.HTTPError:
        logger.warning("Keycloak could not be reached to revoke a refresh token")


# ------------------------------------------------------------ verification
def verify_access_token(token: str) -> dict[str, Any]:
    """The claims of a valid Keycloak access token of the login client, or 401."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Unauthorized! Invalid access token.") from exc
    if header.get("alg") not in ALGORITHMS or not header.get("kid"):
        raise UnauthorizedError("Unauthorized! Invalid access token.")
    key = _signing_key(token)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            issuer=settings.keycloak_issuer,
            leeway=settings.KEYCLOAK_TOKEN_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "iss", "sub", "jti"], "verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Session has expired, please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        logger.info("Keycloak access token rejected: %s", exc)
        raise UnauthorizedError("Unauthorized! Invalid access token.") from exc
    # An ID or refresh token of the same realm is signed with the same key.
    if claims.get("typ") != "Bearer":
        raise UnauthorizedError("Unauthorized! Invalid access token.")
    # Tokens of other clients of the realm (e.g. the CM partner portal) are not ours.
    if claims.get("azp") != settings.KEYCLOAK_LOGIN_CLIENT_ID:
        raise UnauthorizedError("Unauthorized! Invalid access token.")
    if not claims.get("sid"):
        raise UnauthorizedError("Unauthorized! Invalid access token.")
    return claims


def _signing_key(token: str):
    client = _jwks_client()
    try:
        return client.get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientConnectionError as exc:
        raise UpstreamError("Keycloak's signing keys could not be read.") from exc
    except jwt.PyJWKClientError as exc:
        # Unknown kid even after a refresh of the key set.
        raise UnauthorizedError("Unauthorized! Invalid access token.") from exc


def _jwks_client() -> jwt.PyJWKClient:
    url = settings.keycloak_jwks_url
    with _jwks_lock:
        if _jwks["client"] is None or _jwks["url"] != url:
            _jwks["client"] = jwt.PyJWKClient(
                url,
                cache_keys=True,
                lifespan=settings.KEYCLOAK_JWKS_CACHE_SECONDS,
                timeout=settings.KEYCLOAK_TIMEOUT,
            )
            _jwks["url"] = url
        return _jwks["client"]


# ------------------------------------------------------------------ helpers
def _endpoint(name: str) -> str:
    realm = quote(settings.KEYCLOAK_REALM)
    return f"{settings.KEYCLOAK_URL.rstrip('/')}/realms/{realm}/protocol/openid-connect/{name}"


def _client_auth() -> dict[str, str]:
    return {"client_id": settings.KEYCLOAK_LOGIN_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_LOGIN_CLIENT_SECRET}


def _token_request(form: dict[str, str]) -> Tokens:
    try:
        response = httpx.post(_endpoint("token"), data={**form, **_client_auth()},
                              timeout=settings.KEYCLOAK_TIMEOUT)
    except httpx.HTTPError as exc:
        raise UpstreamError("Sign-in is unavailable right now, please try again shortly.") from exc
    body = _json(response)
    if response.status_code == 200 and body.get("access_token"):
        claims = verify_access_token(body["access_token"])
        return Tokens(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", ""),
            expires_in=int(body.get("expires_in") or 0),
            refresh_expires_in=int(body.get("refresh_expires_in") or 0),
            claims=claims,
        )
    error, description = body.get("error", ""), body.get("error_description", "")
    if form["grant_type"] == "refresh_token":
        # Expired, revoked or rotated-away refresh token, or an ended session.
        raise UnauthorizedError(SESSION_INVALID)
    if error == "invalid_grant":
        if "disabled" in description.lower():
            raise ForbiddenError("Your account has been blocked, contact the administrator.")
        if "not fully set up" in description.lower():
            raise ForbiddenError(
                "Your account needs an action before you can sign in (e.g. a new password); "
                "use 'Forgot password' or contact the administrator."
            )
        raise InvalidCredentials(INVALID_CREDENTIALS)
    # invalid_client / unauthorized_client: our client is set up wrongly - not the user's fault.
    logger.error("Keycloak refused the sandbox's login client: %s %s (%s)",
                 response.status_code, error, description)
    raise UpstreamError("Sign-in is unavailable right now, please try again shortly.")


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def reset_cache() -> None:
    """Forget the cached signing keys (tests, key rotation)."""
    with _jwks_lock:
        _jwks["client"] = None
        _jwks["url"] = None

