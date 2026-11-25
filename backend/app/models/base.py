"""Shared column types and mixins."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

from app.config.settings import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


# Postgres gets native JSONB and UUID; SQLite (tests) falls back to portable types.
JSONB = JSON().with_variant(postgresql.JSONB(), "postgresql")

# SQLite only auto-increments INTEGER primary keys, so surrogate keys declared
# as BIGINT need a narrower variant there. Postgres still gets BIGSERIAL.
BigIntPk = BigInteger().with_variant(Integer, "sqlite")


class GUID(TypeDecorator):
    """UUID column that stores natively on Postgres and as text elsewhere."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        return str(value)

    def process_result_value(self, value, dialect):
        return None if value is None else str(value)


class UniqueIdMixin:
    """Public-facing opaque identifier, distinct from the surrogate PK."""

    unique_id: Mapped[str] = mapped_column(
        GUID(), default=lambda: str(uuid.uuid4()), unique=True, index=True
    )


class TimestampMixin:
    added_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    modify_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AuditMixin(TimestampMixin):
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    modify_by: Mapped[int | None] = mapped_column(BigInteger)


class SoftDeleteMixin:
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CountryScopedMixin:
    """Tenant key.

    OAN is a shared network across member countries, so every record that is
    not global carries the ISO-3166 alpha-2 code of the country that owns it.
    """

    country_code: Mapped[str] = mapped_column(
        String(2),
        default=lambda: settings.DEFAULT_COUNTRY_CODE,
        nullable=False,
        index=True,
    )
