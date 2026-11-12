"""Schemas for API products, participant apps and app credentials."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.config.settings import settings
from app.models.enums import ApprovalType, Environment
from app.schemas.common import ListQuery, ORMModel

_PRODUCT_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,98}[a-z0-9]$")


def _clean_ips(value: list[str] | None) -> list[str] | None:
    """IPs / CIDRs, normalised (``10.0.0.7/24`` -> ``10.0.0.0/24``), no duplicates."""
    if value is None:
        return None
    cleaned: list[str] = []
    for raw in value:
        item = raw.strip()
        if not item:
            continue
        try:
            network = ipaddress.ip_network(item, strict=False)
        except ValueError:
            raise ValueError(f"'{item}' is not an IP address or CIDR range (e.g. 203.0.113.10 or 203.0.113.0/24).") from None
        text = str(network.network_address) if network.num_addresses == 1 else str(network)
        if text not in cleaned:
            cleaned.append(text)
    if len(cleaned) > settings.MAX_ALLOWED_IPS_PER_APP:
        raise ValueError(f"List at most {settings.MAX_ALLOWED_IPS_PER_APP} addresses.")
    return cleaned


# ------------------------------------------------------------ API products
class ApiProductCreate(BaseModel):
    #: Machine name: lower-case letters, digits and hyphens.
    name: str = Field(..., min_length=3, max_length=100)
    display_name: str = Field(..., min_length=2, max_length=250)
    description: str | None = Field(None, max_length=4000)
    approval_type: ApprovalType = ApprovalType.MANUAL
    is_published: bool = False
    country_code: str | None = Field(None, min_length=2, max_length=2)
    sort_order: int = 0
    endpoint_ids: list[int] = Field(default_factory=list)
    #: Gateway limits for apps with this product; empty = no limit.
    rate_limit_per_minute: int | None = Field(None, ge=1, le=1_000_000)
    quota_per_day: int | None = Field(None, ge=1, le=100_000_000)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip().lower()
        if not _PRODUCT_NAME.match(v):
            raise ValueError("Use lower-case letters, digits and hyphens (e.g. farmer-registry-read).")
        return v

    @field_validator("country_code")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else None


class ApiProductUpdate(ApiProductCreate):
    pass


class ApiProductListQuery(ListQuery):
    is_published: bool | None = None


class ApiProductEndpointOut(BaseModel):
    endpoint_id: int
    product_id: int
    product_name: str | None = None
    display_name: str | None = None
    method: str | None = None
    endpoint_url: str | None = None


class ApiProductOut(ORMModel):
    api_product_id: int
    unique_id: str
    name: str
    display_name: str
    description: str | None = None
    approval_type: str
    is_published: bool = False
    is_enabled: bool = True
    country_code: str | None = None
    sort_order: int = 0
    rate_limit_per_minute: int | None = None
    quota_per_day: int | None = None
    endpoint_count: int = 0
    app_count: int = 0
    added_date: datetime | None = None
    modify_date: datetime | None = None


class ApiProductDetailOut(ApiProductOut):
    endpoints: list[ApiProductEndpointOut] = Field(default_factory=list)


# -------------------------------------------------------------------- apps
class AppCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    #: ``api_product_id`` values from ``GET /participant/api-products``.
    api_product_ids: list[int] = Field(default_factory=list)
    #: Optional IP whitelist for the app's keys; empty = any address.
    allowed_ips: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 2:
            raise ValueError("App name is too short.")
        return v

    @field_validator("allowed_ips")
    @classmethod
    def _ips(cls, v: list[str]) -> list[str]:
        return _clean_ips(v) or []


class AppUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    allowed_ips: list[str] | None = None

    @field_validator("allowed_ips")
    @classmethod
    def _ips(cls, v: list[str] | None) -> list[str] | None:
        return _clean_ips(v)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return " ".join(v.split()) if v else v


class AppPromote(BaseModel):
    """"Move to production": what differs from the UAT app. A field left out is copied
    from the UAT app; production servers often have other addresses."""

    description: str | None = Field(None, max_length=1000)
    #: Production's IP whitelist; empty = any address.
    allowed_ips: list[str] | None = None

    @field_validator("allowed_ips")
    @classmethod
    def _ips(cls, v: list[str] | None) -> list[str] | None:
        return _clean_ips(v)


class AppProductsRequest(BaseModel):
    api_product_ids: list[int] = Field(..., min_length=1)


class AppSubscriptionOut(BaseModel):
    api_product_id: int
    name: str
    display_name: str
    rate_limit_per_minute: int | None = None
    quota_per_day: int | None = None
    status: int
    status_label: str
    remarks: str | None = None
    requested_date: datetime | None = None
    decided_date: datetime | None = None
    #: The APIs this product lets the app call.
    endpoints: list[ApiProductEndpointOut] = Field(default_factory=list)


class AppCredentialOut(BaseModel):
    """A credential as listed.

    The app's owner sees the key and the secret of an active credential (the
    portal masks them until revealed); administrators and revoked
    credentials get only the prefix and the secret hint.
    """

    credential_id: str
    api_key: str | None = None
    api_secret: str | None = None
    api_key_prefix: str
    api_secret_hint: str
    status: int
    status_label: str
    issued_date: datetime | None = None
    revoked_date: datetime | None = None
    last_used_date: datetime | None = None
    #: The key stops working then (null = never).
    expires_date: datetime | None = None
    #: The secret was already shown; it cannot be shown again (rotate for a new one).
    secret_viewed: bool = False


class IssuedCredentialOut(AppCredentialOut):
    """Returned when the participant issues a new key: key and secret in clear."""

    api_key: str
    api_secret: str


class AppOut(BaseModel):
    app_id: str
    name: str
    description: str | None = None
    environment: str
    status: int
    status_label: str
    revoked_reason: str | None = None
    allowed_ips: list[str] = Field(default_factory=list)
    #: Limits the gateway applies to this app (null = none), from its approved products.
    rate_limit_per_minute: int | None = None
    quota_per_day: int | None = None
    #: Calls logged in the last minute / 24 hours, when the matching limit is set (approximate:
    #: the gateway's own counter is the one that enforces; a call may take a moment to appear).
    calls_last_minute: int | None = None
    calls_today: int | None = None
    gateway_consumer: str | None = None
    gateway_status: str
    gateway_error: str | None = None
    gateway_synced_at: datetime | None = None
    gateway_warnings: list[str] = Field(default_factory=list)
    products: list[AppSubscriptionOut] = Field(default_factory=list)
    credentials: list[AppCredentialOut] = Field(default_factory=list)
    added_date: datetime | None = None
    modify_date: datetime | None = None


class AdminAppOut(AppOut):
    #: Numeric id, for the console's actions.
    id: int
    participant_id: int
    participant_name: str | None = None
    participant_email: str | None = None
    company_name: str | None = None
    gateway_routes: list[str] = Field(default_factory=list)


class AppCreatedOut(BaseModel):
    """A new app. It waits for an administrator, so there is no credential yet."""

    app: AppOut
    credential: IssuedCredentialOut | None = None


# ------------------------------------------------------------------- admin
class AdminAppListQuery(ListQuery):
    status: int | None = None
    participant_id: int | None = None
    api_product_id: int | None = None
    #: Only apps with at least one product request awaiting a decision.
    pending_only: bool = False
    #: UAT or PRODUCTION apps only; empty = both.
    environment: Environment | None = None


class SubscriptionDecision(BaseModel):
    remarks: str | None = Field(None, max_length=1000)


class SubscriptionReject(BaseModel):
    remarks: str = Field(..., min_length=3, max_length=1000)


class AppRevokeRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=1000)
