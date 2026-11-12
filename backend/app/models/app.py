"""API products, developer apps and their credentials (the Apigee model).

* An **API product** is an access bundle: a named set of catalogue endpoints
  that an app can be granted. It is separate from the catalogue ``Product``
  (which groups endpoints for documentation), so one endpoint can sit in
  several API products - e.g. "Farmer Registry - Read" with 7 of the 13
  registry endpoints and "Farmer Registry - Full" with all 13.
* A participant creates any number of **apps**. A new app waits for an
  administrator (``AppStatus.PENDING``): approving the app, or any one of
  its product requests, activates it. Each app asks for API products
  (``participant_app_product``); each grant is approved automatically or by
  an administrator, per the product's approval type.
* Each active app holds one or more **credentials**: an API key and a
  secret, first issued when the administrator approves the app (never at
  creation). Two can be active at once so a key can be rotated without
  downtime.

At the gateway an app is one APISIX consumer. Its credentials are the
consumer's ``key-auth`` (API key) and ``hmac-auth`` (key + secret)
credentials, and a ``consumer-restriction`` whitelist of route ids, built from
the approved API products' endpoints, limits what the app may call.

Key and secret are stored encrypted (``app.core.crypto``), never in clear:
the sandbox must read them back to provision the gateway and to sign try-it
calls. ``api_key_hash`` (SHA-256) finds a credential by key without
decrypting every row.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import (
    JSONB,
    AuditMixin,
    BigIntPk,
    SoftDeleteMixin,
    UniqueIdMixin,
    utcnow,
)
from app.models.enums import (
    ApprovalType,
    AppStatus,
    CredentialStatus,
    Environment,
    GatewaySyncStatus,
    SubscriptionStatus,
)


class ApiProduct(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "api_product"

    api_product_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    #: Stable machine name, e.g. ``farmer-registry-read``.
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: AUTO or MANUAL - see ``enums.ApprovalType``.
    approval_type: Mapped[str] = mapped_column(
        String(10), default=str(ApprovalType.MANUAL), nullable=False
    )
    #: Offered to participants when creating an app.
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    #: Calls per minute / per day an app with this product may make at the
    #: gateway (GATEWAY_RATE_LIMIT_ENABLED); empty = no limit.
    rate_limit_per_minute: Mapped[int | None] = mapped_column(Integer)
    quota_per_day: Mapped[int | None] = mapped_column(Integer)

    endpoints: Mapped[list[ApiProductEndpoint]] = relationship(
        back_populates="api_product", cascade="all, delete-orphan"
    )


class ApiProductEndpoint(Base):
    """Mapping: which catalogue endpoints an API product grants."""

    __tablename__ = "api_product_endpoint"
    __table_args__ = (
        UniqueConstraint("api_product_id", "endpoint_id", name="uq_api_product_endpoint"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    api_product_id: Mapped[int] = mapped_column(
        ForeignKey("api_product.api_product_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("endpoint.endpoint_id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    api_product: Mapped[ApiProduct] = relationship(back_populates="endpoints")


class ParticipantApp(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "participant_app"
    __table_args__ = (
        # Unique among apps not deleted: a deleted app's name can be used again.
        Index(
            "uq_participant_app_name",
            "participant_id",
            "name",
            "environment",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )

    app_id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participant.participant_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    environment: Mapped[str] = mapped_column(
        String(20), default=str(Environment.UAT), nullable=False, index=True
    )
    status: Mapped[int] = mapped_column(
        Integer, default=int(AppStatus.PENDING), nullable=False, index=True
    )
    #: Why an administrator revoked, or rejected, the app.
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    #: Optional IP whitelist (IPs or CIDRs) for calls with this app's keys;
    #: empty = any address. Enforced by APISIX ip-restriction on the consumer.
    allowed_ips: Mapped[list | None] = mapped_column(JSONB, default=list)

    # --- gateway --------------------------------------------------------
    #: APISIX consumer username (letters, digits and ``_`` only).
    gateway_consumer: Mapped[str | None] = mapped_column(String(100), unique=True)
    gateway_status: Mapped[str] = mapped_column(
        String(10), default=str(GatewaySyncStatus.PENDING), nullable=False
    )
    gateway_error: Mapped[str | None] = mapped_column(Text)
    gateway_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Route ids last whitelisted for the consumer, and the endpoints that
    #: could not be granted (no route, or a route that also serves endpoints
    #: outside the app's products).
    gateway_routes: Mapped[list | None] = mapped_column(JSONB, default=list)
    gateway_warnings: Mapped[list | None] = mapped_column(JSONB, default=list)

    subscriptions: Mapped[list[ParticipantAppProduct]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )
    credentials: Mapped[list[ParticipantAppCredential]] = relationship(
        back_populates="app", cascade="all, delete-orphan"
    )


class ParticipantAppProduct(Base, AuditMixin):
    """Mapping: an app's request for, and access to, one API product."""

    __tablename__ = "participant_app_product"
    __table_args__ = (
        UniqueConstraint("app_id", "api_product_id", name="uq_participant_app_product"),
    )

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    app_id: Mapped[int] = mapped_column(
        ForeignKey("participant_app.app_id", ondelete="CASCADE"), nullable=False, index=True
    )
    api_product_id: Mapped[int] = mapped_column(
        ForeignKey("api_product.api_product_id"), nullable=False, index=True
    )
    status: Mapped[int] = mapped_column(
        Integer, default=int(SubscriptionStatus.PENDING), nullable=False, index=True
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(BigInteger)
    decided_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    app: Mapped[ParticipantApp] = relationship(back_populates="subscriptions")
    api_product: Mapped[ApiProduct] = relationship()


class ParticipantIamUser(Base, AuditMixin):
    """A participant's user in Keycloak, one per participant.

    Created when an administrator first approves an environment (UAT), not at
    sign-up (``iam_user_service``). ``roles`` mirrors the environment roles
    (uat / production) of the shared partner client the user holds.
    ``password_synced_at`` is empty while Keycloak does not have the current
    password yet (the sandbox only stores a hash, so every new user starts
    without one); the next portal sign-in sets it.
    """

    __tablename__ = "participant_iam_user"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participant.participant_id"), nullable=False, unique=True
    )
    realm: Mapped[str] = mapped_column(String(100), nullable=False)
    #: Keycloak username (the participant's email address).
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Keycloak's internal id of the user (Admin API path).
    keycloak_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    #: Environment roles held, comma separated, e.g. ``uat,production``.
    roles: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    error: Mapped[str | None] = mapped_column(Text)
    password_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- Consent Manager partner portal / Partner Management --------------
    #: The participant's partner ID (``partner_id`` attribute / CM claim), e.g.
    #: ``oan-p-42``; set once the portal is configured.
    partner_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    #: Holds the partner portal client role (KEYCLOAK_PORTAL_ROLE).
    portal_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: The partner in Partner Management (PARTNER_OAN_P_42), once onboarded.
    pm_partner_id: Mapped[str | None] = mapped_column(String(255))
    #: ACTIVE / DISABLED / FAILED (IamUserStatus); empty: never sent to PM.
    pm_status: Mapped[str | None] = mapped_column(String(10))
    pm_error: Mapped[str | None] = mapped_column(Text)
    pm_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ParticipantAppCredential(Base, UniqueIdMixin, AuditMixin):
    __tablename__ = "participant_app_credential"

    credential_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    app_id: Mapped[int] = mapped_column(
        ForeignKey("participant_app.app_id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Fernet ciphertext of the API key and the secret.
    api_key_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    api_secret_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    #: SHA-256 of the API key: unique, and a lookup without decrypting.
    api_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    #: First characters of the key, safe to show in lists.
    api_key_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[int] = mapped_column(
        Integer, default=int(CredentialStatus.ACTIVE), nullable=False, index=True
    )
    issued_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The key stops working at this time (APP_KEY_LIFETIME_DAYS at issue, or the
    #: rotation grace period of a replaced key); empty = no expiry.
    expires_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    #: When the owner was shown the secret in clear (once: at issue, rotation or
    #: the first "Reveal"); empty = not yet shown.
    secret_viewed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the "key expires soon" email went out.
    expiry_notified_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    app: Mapped[ParticipantApp] = relationship(back_populates="credentials")
