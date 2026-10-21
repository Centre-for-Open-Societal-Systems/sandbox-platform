"""Audit and telemetry tables.

* ``ApiLog``        - one row per call that passed through the sandbox proxy
* ``UserActionLog`` - who did what in the consoles (the audit trail)
* ``SandboxLog``    - structured application events written by the logger
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import JSONB, BigIntPk, utcnow


class ApiLog(Base):
    __tablename__ = "api_log"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    transaction_id: Mapped[str | None] = mapped_column(String(128), index=True)

    participant_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), index=True)
    product_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    endpoint_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    environment: Mapped[str | None] = mapped_column(String(20), index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)

    method: Mapped[str | None] = mapped_column(String(10))
    endpoint_url: Mapped[str | None] = mapped_column(Text)
    target_url: Mapped[str | None] = mapped_column(Text)
    status_code: Mapped[int | None] = mapped_column(Integer, index=True)
    error_message: Mapped[str | None] = mapped_column(Text)

    request_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    response_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Round-trip latency in milliseconds.
    latency_ms: Mapped[float | None] = mapped_column(Float)
    upstream_latency_ms: Mapped[float | None] = mapped_column(Float)

    client_ip: Mapped[str | None] = mapped_column(String(45))
    request_size: Mapped[int | None] = mapped_column(Integer)
    response_size: Mapped[int | None] = mapped_column(Integer)

    request_headers: Mapped[dict | None] = mapped_column(JSONB)
    request_body: Mapped[dict | None] = mapped_column(JSONB)
    response_body: Mapped[dict | None] = mapped_column(JSONB)

    log_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class UserActionLog(Base):
    __tablename__ = "user_action_log"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    #: "admin" | "user" | "system"
    actor_type: Mapped[str] = mapped_column(String(20), default="system", index=True)
    actor_id: Mapped[str | None] = mapped_column(String(64), index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255))

    #: Verb + target, e.g. action="USER_APPROVE", entity="participant".
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(String(100), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(1000))
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)

    #: Before/after snapshot for change-tracking screens.
    changes: Mapped[dict | None] = mapped_column(JSONB)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


class SandboxLog(Base):
    __tablename__ = "sandbox_log"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(20), default="info", index=True)
    message: Mapped[str | None] = mapped_column(Text)
    logdata: Mapped[dict | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(64), index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
