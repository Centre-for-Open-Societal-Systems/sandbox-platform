"""Password hashing, JWT issuance/verification and RSA payload unsealing."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config.settings import settings
from app.core.exceptions import UnauthorizedError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)


# --------------------------------------------------------------- passwords
def hash_password(plain: str) -> str:
    """bcrypt hash, wire-compatible with the reference stack's bcryptjs hashes."""
    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str | None) -> bool:
    if not plain or not hashed:
        return False
    try:
        # bcryptjs emits $2a$ / $2y$ prefixes; the C library accepts both.
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------- jwt
def _encode(payload: dict[str, Any], key: str, expires_in: int) -> str:
    now = datetime.now(UTC)
    body = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    return jwt.encode(body, key, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str | int, extra: dict[str, Any] | None = None) -> str:
    return _encode(
        {"id": str(subject), "typ": "access", **(extra or {})},
        settings.JWT_ACCESS_TOKEN_KEY,
        settings.JWT_ACCESS_TOKEN_EXPIRES,
    )


def create_refresh_token(
    subject: str | int, extra: dict[str, Any] | None = None
) -> str:
    return _encode(
        {"id": str(subject), "typ": "refresh", **(extra or {})},
        settings.JWT_REFRESH_TOKEN_KEY,
        settings.JWT_REFRESH_TOKEN_EXPIRES,
    )


def decode_token(
    token: str, refresh: bool = False, role: str | None = None
) -> dict[str, Any]:
    """Verify signature and expiry, and that the token is of the expected kind.

    ``typ`` must match (an access token never passes as a refresh token or the
    other way round) and, with ``role``, so must the audience the token was
    issued to (admin / participant).
    """
    key = settings.JWT_REFRESH_TOKEN_KEY if refresh else settings.JWT_ACCESS_TOKEN_KEY
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Session has expired, please sign in again.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Unauthorized! Invalid access token.") from exc
    if claims.get("typ") != ("refresh" if refresh else "access"):
        raise UnauthorizedError("Unauthorized! Invalid access token.")
    if role is not None and claims.get("role") != role:
        raise UnauthorizedError("Unauthorized! Invalid access token.")
    return claims


def session_expired(added: datetime | None, last_action: datetime | None) -> bool:
    """True when a sign-in session (``x-auth-key``) is past its idle or absolute limit."""
    now = datetime.now(UTC)

    def _aware(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    added, last_action = _aware(added), _aware(last_action)
    if added is not None and now - added > timedelta(seconds=settings.SESSION_MAX_AGE_SECONDS):
        return True
    idle_since = last_action or added
    return idle_since is not None and now - idle_since > timedelta(
        seconds=settings.SESSION_IDLE_TIMEOUT_SECONDS
    )


# A valid hash checked when the account does not exist, so a sign-in for an
# unknown address takes as long as one with a wrong password.
_DUMMY_HASH = bcrypt.hashpw(
    secrets.token_bytes(32), bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
).decode()


def verify_password_or_dummy(plain: str, hashed: str | None) -> bool:
    if not hashed:
        verify_password(plain or "x", _DUMMY_HASH)
        return False
    return verify_password(plain, hashed)


def codes_match(given: str | None, expected: str | None) -> bool:
    """Constant-time comparison of OTPs and similar short secrets."""
    if not given or not expected:
        return False
    return secrets.compare_digest(str(given), str(expected))


def sha256_token(value: str) -> str:
    """Stored form of a reset / invitation token: only its hash is kept."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# -------------------------------------------------------------------- misc
def new_auth_key() -> str:
    """Opaque session handle stored alongside the JWT (the ``x-auth-key``)."""
    return str(uuid.uuid4())


def generate_otp(length: int | None = None) -> str:
    # Without mail delivery nobody can receive a random code; see DEV_FIXED_OTP.
    if settings.fixed_otp:
        return settings.fixed_otp
    length = length or settings.OTP_LENGTH
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def generate_token_urlsafe(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


# ------------------------------------------------------- RSA sealed payload
def rsa_decrypt_payload(post_data: str) -> dict[str, Any]:
    """Unseal the browser's RSA-encrypted ``post_data`` envelope.

    When ``RSA_PAYLOAD_ENABLED`` is off (local development) the field is
    treated as plain - or base64-wrapped - JSON so the API stays easy to
    exercise with curl and the OpenAPI console.
    """
    if not post_data:
        raise ValidationError("Request payload is missing.")

    if not settings.RSA_PAYLOAD_ENABLED:
        return _loads_plain_or_b64(post_data)

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ValidationError("RSA support is not installed on this server.") from exc

    try:
        with open(settings.RSA_PRIVATE_KEY_PATH, "rb") as fh:
            private_key = serialization.load_pem_private_key(fh.read(), password=None)
        sealed = base64.b64decode(post_data)
        raw = None
        # SHA-256 is this client's default; the reference (Indian) web client
        # seals with OAEP SHA-1 (node-forge / JSEncrypt), so accept both.
        for digest in (hashes.SHA256, hashes.SHA1):
            try:
                raw = private_key.decrypt(
                    sealed,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=digest()),
                        algorithm=digest(),
                        label=None,
                    ),
                )
                break
            except ValueError:
                continue
        if raw is None:
            raise ValueError("payload does not match the server key")
        return json.loads(raw.decode("utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError("Server encryption key is not configured.") from exc
    except Exception as exc:
        logger.warning("Failed to unseal post_data: %s", exc)
        raise ValidationError("Request payload could not be read.") from exc


def _loads_plain_or_b64(value: str) -> dict[str, Any]:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(base64.b64decode(value).decode("utf-8"))
    except Exception as exc:
        raise ValidationError("Request payload could not be read.") from exc
