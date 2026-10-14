"""Schemas for portal registration, sign-in and profile."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import Environment, ProfileType
from app.schemas.common import ListQuery, ORMModel
from app.utils.validators import (
    normalise_msisdn,
    validate_password_strength,
    validate_registration_number,
)


# ------------------------------------------------------------- registration
class SignupRequest(BaseModel):
    """The single-screen signup form.

    Everything a new account needs and nothing more; organisation KYC is
    collected later, when the user asks for UAT access.
    """

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    #: Dialling country, which also selects the mobile-number format rules.
    country_code: str = Field("ET", min_length=2, max_length=2)
    mobile_number: str = Field(..., min_length=6, max_length=20)
    #: Business email - this is the login identifier.
    email_id: EmailStr
    #: ``category.category_id`` from ``GET /masters/category``.
    category_id: int = Field(..., ge=1)
    company_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    #: Terms and privacy policy.
    declaration: bool = False

    _check_password = field_validator("password")(validate_password_strength)

    @field_validator("country_code")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()

    @field_validator("first_name", "last_name", "company_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def _finalise(self):
        # Normalising here rather than in a field validator so the already
        # upper-cased country_code is available to pick the format rules.
        self.mobile_number = normalise_msisdn(self.mobile_number, self.country_code)
        if not self.declaration:
            raise ValueError("You must accept the terms and privacy policy.")
        return self


class VerifyEmailRequest(BaseModel):
    """Step 2 - the code emailed at signup."""

    unique_id: str
    otp: str = Field(..., min_length=4, max_length=10)


class ResendOtpRequest(BaseModel):
    unique_id: str


class CheckEmailRequest(BaseModel):
    email_id: EmailStr


class ProfileRequest(BaseModel):
    """Profile completion - required before UAT access can be requested."""

    profile_type: ProfileType | None = None
    company_name: str | None = Field(None, max_length=255)
    organization_registration_number: str | None = Field(None, max_length=100)
    date_of_registration: date | None = None
    registered_in_country: bool | None = None
    tax_identification_number: str | None = Field(None, max_length=50)

    category_id: int | None = None
    sub_category_id: int | None = None
    participant_type_id: int | None = None
    service_domain: str | None = None
    operating_area: str | None = None
    description: str | None = Field(None, max_length=4000)
    website: str | None = Field(None, max_length=255)

    first_name: str | None = Field(None, max_length=100)
    last_name: str | None = Field(None, max_length=100)
    authorized_person_name: str | None = Field(None, max_length=255)
    authorized_person_designation: str | None = Field(None, max_length=100)
    authorized_person_address: str | None = Field(None, max_length=500)
    authorized_person_postal_code: str | None = Field(None, max_length=20)

    admin_area_code_l1: str | None = Field(None, max_length=20)
    admin_area_code_l2: str | None = Field(None, max_length=20)

    @model_validator(mode="after")
    def _profile_consistency(self):
        if self.organization_registration_number:
            # Format rules differ per country; the validator dispatches on it.
            validate_registration_number(self.organization_registration_number)
        return self


class ProfileForm(ProfileRequest):
    """Multipart variant of :class:`ProfileRequest`.

    FastAPI cannot flatten a form model when a separate ``File`` parameter is
    also declared, so the upload travels as a field on the model itself.
    """

    id_proof: UploadFile | None = None


# --------------------------------------------------------------------- auth
class ParticipantLoginRequest(BaseModel):
    email_id: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=200)


class ParticipantLoginResponse(BaseModel):
    participant_id: int
    unique_id: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    company_name: str | None = None
    email_id: str | None = None
    country_code: str
    #: Environments this user may currently call.
    environments: list[str] = Field(default_factory=list)
    is_profile_complete: bool = False
    is_uat_requested: bool = False
    is_prod_requested: bool = False
    access_token: str
    refresh_token: str
    token_expiry: int
    token_issued_at: datetime
    auth_key: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ForgotPasswordRequest(BaseModel):
    email_id: EmailStr


class ResetPasswordRequest(BaseModel):
    #: Emailed link token. Without mail (development) send email_id + otp instead.
    token: str | None = None
    email_id: EmailStr | None = None
    otp: str | None = Field(None, min_length=4, max_length=10)
    new_password: str = Field(..., min_length=8, max_length=128)

    _check_password = field_validator("new_password")(validate_password_strength)

    @model_validator(mode="after")
    def _token_or_code(self):
        if not self.token and not (self.email_id and self.otp):
            raise ValueError("Send the reset token, or the email address and code.")
        return self


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=128)

    _check_password = field_validator("new_password")(validate_password_strength)


# ------------------------------------------------------------------ profile
class ParticipantOut(ORMModel):
    participant_id: int
    unique_id: str
    first_name: str | None = None
    last_name: str | None = None
    display_name: str = ""
    company_name: str | None = None
    email_id: str | None = None
    mobile_number: str | None = None
    profile_type: str | None = None
    organization_registration_number: str | None = None
    website: str | None = None
    country_code: str
    admin_area_code_l1: str | None = None
    admin_area_code_l2: str | None = None
    category_id: int | None = None
    sub_category_id: int | None = None
    participant_type_id: int | None = None
    service_domain: str | None = None
    operating_area: str | None = None
    description: str | None = None
    authorized_person_name: str | None = None
    authorized_person_designation: str | None = None
    authorized_person_address: str | None = None

    is_email_verified: bool = False
    is_profile_complete: bool = False
    is_approved: int = 0
    is_activated: int = 0
    is_rejected: bool = False
    rejection_reason: str | None = None
    is_sandbox_approved: bool = False
    is_uat_requested: bool = False
    is_uat_approved: bool = False
    is_uat_rejected: bool = False
    is_prod_requested: bool = False
    is_prod_approved: bool = False
    is_prod_rejected: bool = False
    is_enabled: bool = True

    register_date: datetime | None = None
    approved_date: datetime | None = None
    uat_approved_date: datetime | None = None
    prod_approved_date: datetime | None = None


class ParticipantListQuery(ListQuery):
    country_code: str | None = None
    admin_area_code_l1: str | None = None
    participant_type_id: int | None = None
    profile_type: str | None = None
    environment: Environment | None = None
    is_approved: int | None = None
    is_rejected: bool | None = None
    date_from: date | None = None
    date_to: date | None = None


class ApproveRequest(BaseModel):
    participant_id: int = Field(..., ge=1)
    environment: Environment = Environment.UAT
    remarks: str | None = Field(None, max_length=1000)


class RejectRequest(BaseModel):
    participant_id: int = Field(..., ge=1)
    environment: Environment = Environment.UAT
    rejection_reason: str = Field(..., min_length=3, max_length=1000)


class PromotionRequest(BaseModel):
    """A user asking to be promoted to UAT or production."""

    target_environment: Environment
    remarks: str | None = Field(None, max_length=2000)
    extra_data: dict[str, Any] = Field(default_factory=dict)


class PromotionRequestOut(ORMModel):
    request_id: int
    participant_id: int
    target_environment: str
    status: int
    remarks: str | None = None
    rejection_reason: str | None = None
    certificate_path: str | None = None
    document_path: str | None = None
    extra_data: dict[str, Any] | None = None
    added_date: datetime | None = None
    reviewed_date: datetime | None = None


class PromotionDetails(BaseModel):
    """Move-to-production questionnaire sent with an environment request."""

    model_config = {"extra": "forbid"}

    public_key: str | None = Field(None, max_length=10000)
    endpoint_ids: list[int] = Field(default_factory=list, max_length=500)
    daily_volume: int | None = Field(None, ge=0)
    integration_contact: str | None = Field(None, max_length=255)
    escalation_contact: str | None = Field(None, max_length=255)


class AdminParticipantDetail(ParticipantOut):
    """What a reviewer sees: the profile plus documents and access requests."""

    id_proof: str | None = None
    requests: list[PromotionRequestOut] = Field(default_factory=list)


class QueryCreate(BaseModel):
    query_type: int | None = None
    subject: str = Field(..., min_length=3, max_length=500)
    description: str = Field(..., min_length=3, max_length=4000)


class QueryOut(ORMModel):
    query_id: int
    participant_id: int | None = None
    query_type: int | None = None
    subject: str | None = None
    description: str | None = None
    status: int = 0
    response: str | None = None
    added_date: datetime | None = None
    responded_date: datetime | None = None


class AdminQueryOut(QueryOut):
    """A query as the console lists it, with who raised it."""

    participant_name: str | None = None
    email_id: str | None = None
    company_name: str | None = None


class QueryListQuery(ListQuery):
    #: 0 open, 1 in progress, 2 answered, 3 closed.
    status: int | None = Field(None, ge=0, le=3)
    query_type: int | None = None


class QueryRespondRequest(BaseModel):
    query_id: int = Field(..., ge=1)
    response: str = Field(..., min_length=1, max_length=4000)
    status: int = Field(2, ge=0, le=3)
