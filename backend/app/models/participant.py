"""Network participants - the organisations and developers consuming OAN APIs.

One table, not the reference stack's draft/live pair. Registration writes a
``Participant`` row straight away with ``is_email_verified`` false; verifying
the emailed code flips that flag and grants sandbox access. UAT and production
each need a separate admin decision, recorded in ``ParticipantRequestInfo``.

Dropping the ``temp_customer`` staging table removes a bug class the reference
still has: a username free in the draft table could collide on promotion,
because the two tables were checked independently.

India-specific reference fields are generalised:

==============================  ==============================
Reference                       OAN
==============================  ==============================
``registered_in_india``         ``registered_in_country``
``state_lgd_code``              ``admin_area_code_l1``
``district_lgd_code``           ``admin_area_code_l2``
``authorized_person_pin_code``  ``authorized_person_postal_code``
PAN / GSTIN / CIN validators    ``tax_identification_number`` + country rules
==============================  ==============================
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import (
    JSONB,
    AuditMixin,
    BigIntPk,
    CountryScopedMixin,
    SoftDeleteMixin,
    UniqueIdMixin,
    utcnow,
)
from app.models.enums import ActivationStatus, ApprovalStatus


class Participant(Base, UniqueIdMixin, CountryScopedMixin, SoftDeleteMixin):
    """A portal account.

    Named ``participant`` rather than ``user`` because ``user`` is a reserved
    word in PostgreSQL and would need quoting at every call site.
    """

    __tablename__ = "participant"

    participant_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )

    # --- signup form -----------------------------------------------------
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    #: Login identifier. There is no separate username.
    email_id: Mapped[str | None] = mapped_column(String(255), index=True)
    #: Stored in E.164 form, e.g. ``+251911234567``.
    mobile_number: Mapped[str | None] = mapped_column(String(20), index=True)
    company_name: Mapped[str | None] = mapped_column(String(255))
    #: "Business category" - points at ``category.category_id``.
    category_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    user_pass: Mapped[str | None] = mapped_column(String(500))
    #: Terms and privacy policy accepted at signup.
    declaration: Mapped[bool] = mapped_column(Boolean, default=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))

    # --- email verification ---------------------------------------------
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    otp: Mapped[str | None] = mapped_column(String(10))
    otp_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    otp_request_count: Mapped[int] = mapped_column(Integer, default=0)

    # --- profile, completed later and required before UAT ----------------
    #: INDIVIDUAL or ORGANIZATION - see ``enums.ProfileType``.
    profile_type: Mapped[str | None] = mapped_column(String(50))
    organization_registration_number: Mapped[str | None] = mapped_column(String(100))
    sub_category_id: Mapped[int | None] = mapped_column(BigInteger)
    date_of_registration: Mapped[date | None] = mapped_column(Date)
    #: Is the entity legally registered in the country it is applying under?
    registered_in_country: Mapped[bool | None] = mapped_column(Boolean)
    #: TIN in Ethiopia; whatever the member country uses as its business tax id.
    tax_identification_number: Mapped[str | None] = mapped_column(String(50))
    id_proof: Mapped[str | None] = mapped_column(String(1000))

    authorized_person_name: Mapped[str | None] = mapped_column(String(255))
    authorized_person_designation: Mapped[str | None] = mapped_column(String(100))
    authorized_person_address: Mapped[str | None] = mapped_column(String(500))
    authorized_person_postal_code: Mapped[str | None] = mapped_column(String(20))

    website: Mapped[str | None] = mapped_column(String(255))
    #: Level 1 / level 2 codes into ``admin_area`` (Ethiopia: Region / Zone).
    admin_area_code_l1: Mapped[str | None] = mapped_column(String(20), index=True)
    admin_area_code_l2: Mapped[str | None] = mapped_column(String(20), index=True)

    #: AIP or AIU - points at ``participant_type.participant_type_id``.
    participant_type_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    service_domain: Mapped[str | None] = mapped_column(String(250))
    operating_area: Mapped[str | None] = mapped_column(String(250))
    description: Mapped[str | None] = mapped_column(Text)
    #: True once every field UAT review needs has been supplied.
    is_profile_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- audit -----------------------------------------------------------
    register_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    modify_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=utcnow
    )
    added_by: Mapped[int | None] = mapped_column(BigInteger)
    modify_by: Mapped[int | None] = mapped_column(BigInteger)

    # --- lifecycle -------------------------------------------------------
    #: Sandbox approval. Granted automatically on email verification, so this
    #: is APPROVED for every active account; an admin can revoke it.
    is_approved: Mapped[int] = mapped_column(
        Integer, default=int(ApprovalStatus.PENDING)
    )
    is_activated: Mapped[int] = mapped_column(
        Integer, default=int(ActivationStatus.NOT_ACTIVATED)
    )
    is_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    approved_by: Mapped[int | None] = mapped_column(BigInteger)
    approved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[int | None] = mapped_column(BigInteger)
    activated_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # --- environment promotion ------------------------------------------
    is_sandbox_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_uat_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    is_uat_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_uat_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_prod_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    is_prod_approved: Mapped[bool] = mapped_column(Boolean, default=False)
    is_prod_rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    is_prod_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    uat_approved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    prod_approved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Identity issued by the gateway/IdP per environment.
    uat_entity_id: Mapped[str | None] = mapped_column(String(255))
    prod_entity_id: Mapped[str | None] = mapped_column(String(255))
    uat_idp_response: Mapped[dict | None] = mapped_column(JSONB)
    prod_idp_response: Mapped[dict | None] = mapped_column(JSONB)

    #: Endpoint ids this user is entitled to call.
    enabled_apis: Mapped[list | None] = mapped_column(JSONB, default=list)

    # --- credentials -----------------------------------------------------
    public_key: Mapped[str | None] = mapped_column(Text)
    private_key: Mapped[str | None] = mapped_column(Text)
    api_key: Mapped[str | None] = mapped_column(String(255), index=True)
    api_secret: Mapped[str | None] = mapped_column(String(500))

    reset_pass_token: Mapped[str | None] = mapped_column(String(255), index=True)
    reset_pass_token_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    tokens: Mapped[list[ParticipantToken]] = relationship(back_populates="user")
    requests: Mapped[list[ParticipantRequestInfo]] = relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p).strip()

    @property
    def display_name(self) -> str:
        return self.full_name or self.company_name or self.email_id or ""


class ParticipantToken(Base, UniqueIdMixin):
    """One row per participant sign-in; ``unique_id`` is the ``x-auth-key``."""

    __tablename__ = "participant_token"

    token_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participant.participant_id"), index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(2500))
    device_name: Mapped[str | None] = mapped_column(String(100))
    ip_location: Mapped[str | None] = mapped_column(String(100))
    added_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_action: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    is_logout: Mapped[bool] = mapped_column(Boolean, default=False)
    logout_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[Participant | None] = relationship(back_populates="tokens")


class ParticipantRequestInfo(Base, UniqueIdMixin, AuditMixin):
    """A UAT or production promotion request, and the admin decision on it."""

    __tablename__ = "participant_request_info"

    request_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participant.participant_id"), nullable=False, index=True
    )
    #: Target environment for the request - UAT or PRODUCTION.
    target_environment: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[int] = mapped_column(
        Integer, default=int(ApprovalStatus.PENDING), index=True
    )
    remarks: Mapped[str | None] = mapped_column(Text)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    certificate_path: Mapped[str | None] = mapped_column(String(1000))
    document_path: Mapped[str | None] = mapped_column(String(1000))
    #: Free-form answers to the promotion questionnaire.
    extra_data: Mapped[dict | None] = mapped_column(JSONB)

    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[Participant] = relationship(back_populates="requests")


class ParticipantQuery(Base, UniqueIdMixin, AuditMixin):
    """Support tickets raised from the participant portal."""

    __tablename__ = "participant_query"

    query_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("participant.participant_id"), index=True
    )
    query_type: Mapped[int | None] = mapped_column(Integer)
    subject: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[int] = mapped_column(Integer, default=0, index=True)
    response: Mapped[str | None] = mapped_column(Text)
    responded_by: Mapped[int | None] = mapped_column(BigInteger)
    responded_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
