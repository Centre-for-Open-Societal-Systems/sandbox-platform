"""Brute-force protection for the public authentication routes.

Two kinds of counter, both rows of ``auth_throttle``:

* failures per account (``login:admin:<name>``, ``otp:<unique_id>``) - after
  ``LOGIN_MAX_FAILURES`` wrong attempts the key is locked for
  ``LOGIN_LOCKOUT_SECONDS``; a success clears it;
* requests per client IP and route (``ip:<route>:<addr>``) - at most
  ``AUTH_RATE_LIMIT_PER_MINUTE`` a minute, so one caller cannot spray many
  accounts or flood reset mail.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.context import client_ip_ctx
from app.core.exceptions import AppError
from app.core.status_codes import StatusCode
from app.models.logs import AuthThrottle


class TooManyAttemptsError(AppError):
    status_code = StatusCode.TOO_MANY_REQUESTS
    message = "Too many attempts. Please try again later."


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _row(db: Session, key: str) -> AuthThrottle:
    row = db.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalars().first()
    if row is not None:
        return row
    row = AuthThrottle(key=key[:320], failures=0, window_start=datetime.now(UTC))
    db.add(row)
    try:
        db.commit()
    except IntegrityError:  # created by a concurrent request
        db.rollback()
        row = db.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalars().one()
    return row


def assert_not_locked(db: Session, key: str) -> None:
    row = db.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalars().first()
    locked_until = _aware(row.locked_until) if row else None
    if locked_until and locked_until > datetime.now(UTC):
        raise TooManyAttemptsError(
            "Too many failed attempts. Please wait a few minutes and try again."
        )


def record_failure(db: Session, key: str, limit: int | None = None) -> int:
    """Count a failed attempt; lock the key once ``limit`` is reached. Returns the count."""
    limit = limit or settings.LOGIN_MAX_FAILURES
    window = timedelta(seconds=settings.LOGIN_LOCKOUT_SECONDS)
    now = datetime.now(UTC)
    row = _row(db, key)
    if now - _aware(row.window_start) > window:
        row.failures, row.window_start, row.locked_until = 0, now, None
    row.failures += 1
    if row.failures >= limit:
        row.locked_until = now + window
    db.commit()
    return row.failures


def clear(db: Session, key: str) -> None:
    row = db.execute(select(AuthThrottle).where(AuthThrottle.key == key)).scalars().first()
    if row is not None:
        db.delete(row)
        db.commit()


def limit_ip(db: Session, route: str) -> None:
    """Per-IP request budget for a public auth route (fixed one-minute window)."""
    ip = client_ip_ctx.get() or "unknown"
    now = datetime.now(UTC)
    row = _row(db, f"ip:{route}:{ip}")
    if now - _aware(row.window_start) > timedelta(minutes=1):
        row.failures, row.window_start = 0, now
    row.failures += 1
    db.commit()
    if row.failures > settings.AUTH_RATE_LIMIT_PER_MINUTE:
        raise TooManyAttemptsError()
