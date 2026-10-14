"""Schemas for the back-office console."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.schemas.common import ListQuery, ORMModel
from app.utils.validators import validate_password_strength


# --------------------------------------------------------------------- auth
class AdminLoginRequest(BaseModel):
    """Plain-credential form. Production clients post ``SealedPayload`` instead."""

    username: str = Field(..., min_length=1, max_length=150)
    password: str = Field(..., min_length=1, max_length=200)


class PermissionFlag(BaseModel):
    id: int
    status: bool


class AdminLoginResponse(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email_id: str | None = None
    mobile_no: str | None = None
    is_master: bool = False
    role: str = ""
    country_code: str | None = None
    admin_area_code: str | None = None
    access_token: str
    refresh_token: str
    token_expiry: int
    token_issued_at: datetime
    #: Opaque session handle, echoed back in the ``x-auth-key`` header.
    auth_key: str
    permissions: list[PermissionFlag] = Field(default_factory=list)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain an uppercase letter.")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain a lowercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain a digit.")
        if all(c.isalnum() for c in v):
            raise ValueError("Password must contain a special character.")
        return v


class ForgotPasswordRequest(BaseModel):
    email_id: EmailStr


class SetPasswordRequest(BaseModel):
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


class CheckUsernameRequest(BaseModel):
    login_name: str
    exclude_admin_id: int | None = None


# -------------------------------------------------------------------- roles
class RoleCreate(BaseModel):
    role_name: str = Field(..., min_length=2, max_length=100)
    role_level: int | None = None
    checker_maker: int = Field(0, ge=0, le=2)
    permission_ids: list[int] = Field(default_factory=list)


class RoleUpdate(RoleCreate):
    role_id: int = Field(..., ge=1)


class RoleOut(ORMModel):
    role_id: int
    unique_id: str
    role_name: str
    role_level: int | None = None
    checker_maker: int = 0
    is_editable: bool = True
    is_enabled: bool = True
    added_date: datetime | None = None


class RoleDetailOut(RoleOut):
    permission_ids: list[int] = Field(default_factory=list)
    user_count: int = 0


class PermissionNode(BaseModel):
    permission_id: int
    menu_name: str | None = None
    parent_id: int | None = None
    has_submenu: bool = False
    is_allowed: bool = False
    children: list[PermissionNode] = Field(default_factory=list)


class PermissionUpdateRequest(BaseModel):
    role_id: int = Field(..., ge=1)
    permissions: list[PermissionFlag]


# -------------------------------------------------------------- admin users
class AdminUserCreate(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str | None = Field(None, max_length=50)
    email_id: EmailStr
    mobile_no: str | None = Field(None, max_length=20)
    login_name: str = Field(..., min_length=3, max_length=50)
    role_id: int = Field(..., ge=1)
    country_code: str | None = Field(None, max_length=2)
    admin_area_code: str | None = Field(None, max_length=20)
    description: str | None = Field(None, max_length=500)
    #: Leave unset to email an invite the user completes themselves.
    password: str | None = Field(None, min_length=8, max_length=128)


class AdminUserUpdate(AdminUserCreate):
    admin_id: int = Field(..., ge=1)
    login_name: str | None = Field(None, min_length=3, max_length=50)
    email_id: EmailStr | None = None
    role_id: int | None = Field(None, ge=1)
    first_name: str | None = Field(None, min_length=1, max_length=50)


class AdminUserOut(ORMModel):
    admin_id: int
    unique_id: str
    first_name: str | None = None
    last_name: str | None = None
    email_id: str | None = None
    mobile_no: str | None = None
    login_name: str
    role_id: int | None = None
    role_name: str | None = None
    is_master: bool = False
    is_enabled: bool = True
    is_activated: bool = False
    country_code: str | None = None
    admin_area_code: str | None = None
    description: str | None = None
    added_date: datetime | None = None


class AdminUserListQuery(ListQuery):
    role_id: int | None = None
    is_enabled: bool | None = None
    country_code: str | None = None


# ---------------------------------------------------------------- dashboard
class DashboardCounters(BaseModel):
    total_participants: int = 0
    #: Signed up but never entered the emailed verification code.
    unverified_participants: int = 0
    sandbox_participants: int = 0
    uat_pending: int = 0
    uat_participants: int = 0
    prod_pending: int = 0
    prod_participants: int = 0
    rejected_participants: int = 0
    total_products: int = 0
    published_products: int = 0
    total_endpoints: int = 0
    api_calls_today: int = 0
    api_calls_month: int = 0
    open_queries: int = 0


class DashboardSeriesPoint(BaseModel):
    label: str
    value: int


class DashboardResponse(BaseModel):
    counters: DashboardCounters
    registrations_trend: list[DashboardSeriesPoint] = Field(default_factory=list)
    api_usage_trend: list[DashboardSeriesPoint] = Field(default_factory=list)
    participants_by_area: list[DashboardSeriesPoint] = Field(default_factory=list)
    top_endpoints: list[DashboardSeriesPoint] = Field(default_factory=list)


PermissionNode.model_rebuild()
