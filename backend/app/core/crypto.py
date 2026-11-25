"""App credentials: generation, encryption at rest, hashing.

API keys and secrets are random, high-entropy strings, so a plain SHA-256 is
enough for lookup and uniqueness; it is not a password hash. The clear values
are kept with Fernet (AES-128-CBC + HMAC-SHA256) under
``APP_CREDENTIAL_ENCRYPTION_KEY``, because the sandbox has to hand them to the
gateway and use them in try-it calls.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings
from app.core.exceptions import AppError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Shown in lists in place of the key ("oan_k8Xa2…").
KEY_PREFIX_LENGTH = 10


def new_api_key() -> str:
    # 32 random bytes; the prefix tells a reader what kind of credential it is.
    return "oan_" + secrets.token_urlsafe(32)


def new_api_secret() -> str:
    return secrets.token_urlsafe(48)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@lru_cache
def _fernet() -> Fernet:
    key = settings.APP_CREDENTIAL_ENCRYPTION_KEY
    if not key:
        # Developer-machine fallback only: derived from the JWT key, so a
        # local setup works without one more secret. Every shared server
        # (sandbox, uat, production) sets its own key.
        if settings.ENV != "local" and not settings.is_sqlite:
            raise AppError("APP_CREDENTIAL_ENCRYPTION_KEY is not set.")
        logger.warning("APP_CREDENTIAL_ENCRYPTION_KEY not set; deriving it from JWT_ACCESS_TOKEN_KEY")
        key = base64.urlsafe_b64encode(
            hashlib.sha256(("app-credentials:" + settings.JWT_ACCESS_TOKEN_KEY).encode()).digest()
        ).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise AppError(
            "A stored credential could not be decrypted; was APP_CREDENTIAL_ENCRYPTION_KEY changed?"
        ) from exc
