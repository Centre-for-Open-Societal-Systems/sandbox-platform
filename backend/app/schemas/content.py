"""Schemas for CMS content and audit-log queries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import UploadFile
from pydantic import BaseModel, Field

from app.schemas.common import ListQuery, ORMModel


# --------------------------------------------------------------------- faqs
class FaqTypeCreate(BaseModel):
    faq_type: str = Field(..., min_length=2, max_length=150)
    sort_order: int = 0
    locale: str = Field("en", max_length=10)
    country_code: str | None = Field(None, max_length=2)


class FaqTypeUpdate(FaqTypeCreate):
    type_id: int = Field(..., ge=1)
    faq_type: str | None = Field(None, min_length=2, max_length=150)


class FaqTypeOut(ORMModel):
    type_id: int
    faq_type: str
    sort_order: int = 0
    locale: str = "en"
    country_code: str | None = None
    is_enabled: bool = True
    faq_count: int = 0


class FaqCreate(BaseModel):
    type_id: int = Field(..., ge=1)
    question: str = Field(..., min_length=3, max_length=1000)
    answer: str = Field(..., min_length=1)
    sort_order: int = 0
    locale: str = Field("en", max_length=10)


class FaqUpdate(FaqCreate):
    faq_id: int = Field(..., ge=1)
    type_id: int | None = Field(None, ge=1)
    question: str | None = Field(None, min_length=3, max_length=1000)
    answer: str | None = None


class FaqOut(ORMModel):
    faq_id: int
    type_id: int
    faq_type: str | None = None
    question: str
    answer: str | None = None
    sort_order: int = 0
    locale: str = "en"
    is_enabled: bool = True
    added_date: datetime | None = None


class FaqGroupOut(BaseModel):
    """Public FAQ page payload - types with their questions nested."""

    type_id: int
    faq_type: str
    sort_order: int = 0
    faqs: list[FaqOut] = Field(default_factory=list)


# ------------------------------------------------------ terms and conditions
class TermCreate(BaseModel):
    sidebar_title: str = Field(..., min_length=2, max_length=500)
    term_content: str = Field(..., min_length=1)
    sort_order: int = 0
    locale: str = Field("en", max_length=10)
    country_code: str | None = Field(None, max_length=2)


class TermUpdate(TermCreate):
    table_id: int = Field(..., ge=1)
    sidebar_title: str | None = Field(None, min_length=2, max_length=500)
    term_content: str | None = None


class TermOut(ORMModel):
    table_id: int
    sidebar_title: str
    term_content: str | None = None
    sort_order: int = 0
    locale: str = "en"
    country_code: str | None = None
    is_enabled: bool = True
    modify_date: datetime | None = None


# ---------------------------------------------------------- email templates
class EmailTemplateUpsert(BaseModel):
    template_id: int | None = None
    template_code: str = Field(..., min_length=2, max_length=100)
    template_name: str = Field(..., min_length=2, max_length=150)
    subject: str = Field(..., min_length=2, max_length=500)
    body_text: str = Field(..., min_length=1)
    variables: list[str] = Field(default_factory=list)
    locale: str = Field("en", max_length=10)
    is_enabled: bool = True
    sort_order: int = 0


class EmailTemplateOut(ORMModel):
    template_id: int
    template_code: str
    template_name: str
    subject: str | None = None
    body_text: str | None = None
    variables: list[str] | None = None
    locale: str = "en"
    is_enabled: bool = True
    modify_date: datetime | None = None


class TestMailRequest(BaseModel):
    to_email: str
    template_code: str | None = None
    subject: str | None = None
    body: str | None = None


class EmailTemplatePreviewRequest(BaseModel):
    """A template as typed in the editor (saved or not), rendered with sample values."""

    subject: str = Field("", max_length=500)
    body_text: str = ""


# ------------------------------------------------------------ home page CMS
class HomeBlockUpsert(BaseModel):
    block_id: int | None = None
    block_key: str = Field(..., min_length=2, max_length=100)
    title: str | None = Field(None, max_length=500)
    subtitle: str | None = Field(None, max_length=1000)
    body: str | None = None
    image_path: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0
    locale: str = Field("en", max_length=10)
    country_code: str | None = Field(None, max_length=2)


class HomeBlockUpsertForm(HomeBlockUpsert):
    """Multipart variant carrying the block image."""

    image: UploadFile | None = None


class HomeBlockOut(ORMModel):
    block_id: int
    block_key: str
    title: str | None = None
    subtitle: str | None = None
    body: str | None = None
    image_path: str | None = None
    content: dict[str, Any] | None = None
    sort_order: int = 0
    locale: str = "en"
    is_enabled: bool = True


class PublicHomeResponse(BaseModel):
    """Everything the public landing page needs, in one call."""

    blocks: list[HomeBlockOut] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    featured_products: list[dict[str, Any]] = Field(default_factory=list)
    countries: list[dict[str, Any]] = Field(default_factory=list)


# ----------------------------------------------------------------- log query
class ApiLogQuery(ListQuery):
    participant_id: int | None = None
    #: TRYIT or DIRECT.
    source: str | None = None
    app_id: int | None = None
    product_id: int | None = None
    endpoint_id: int | None = None
    environment: str | None = None
    country_code: str | None = None
    status_code: int | None = None
    #: Multi-select filters (any of these partners / apps).
    participant_ids: list[int] | None = Field(None, max_length=500)
    app_ids: list[int] | None = Field(None, max_length=500)
    #: 2xx, 3xx, 4xx or 5xx (5xx includes calls that got no answer).
    status_class: str | None = Field(None, pattern="^[2-5]xx$")
    method: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class ApiUsageQuery(ApiLogQuery):
    """Usage / billing report: calls counted per partner, API, app, day..."""

    group_by: str = Field(
        "participant",
        pattern="^(participant|participant_endpoint|endpoint|app|product|day|status)$",
    )
    sort_by: str | None = "total_calls"


class UsageLookupQuery(BaseModel):
    """One page of a searchable filter dropdown (partners or apps)."""

    search: str | None = Field(None, max_length=100)
    page: int = Field(1, ge=1)
    limit: int = Field(20, ge=1, le=50)
    #: Apps only: limit to these partners' apps.
    participant_ids: list[int] | None = Field(None, max_length=500)


class ApiUsageRow(BaseModel):
    participant_id: int | None = None
    participant_name: str | None = None
    email_id: str | None = None
    country_code: str | None = None
    app_id: int | None = None
    app_name: str | None = None
    product_id: int | None = None
    product_name: str | None = None
    method: str | None = None
    endpoint_url: str | None = None
    day: str | None = None
    status_code: int | None = None
    endpoints_used: int | None = None
    apps_used: int | None = None
    total_calls: int = 0
    success_calls: int = 0
    client_errors: int = 0
    server_errors: int = 0
    success_rate: float | None = None
    avg_latency_ms: float | None = None
    first_call: datetime | None = None
    last_call: datetime | None = None


class ApiUsageCount(BaseModel):
    label: str
    value: int


class ApiUsageSummary(BaseModel):
    total_calls: int = 0
    success_calls: int = 0
    client_errors: int = 0
    server_errors: int = 0
    success_rate: float | None = None
    avg_latency_ms: float | None = None
    partners: int = 0
    apps: int = 0
    endpoints: int = 0
    first_call: datetime | None = None
    last_call: datetime | None = None
    by_status_code: list[ApiUsageCount] = Field(default_factory=list)
    by_source: list[ApiUsageCount] = Field(default_factory=list)
    by_day: list[ApiUsageCount] = Field(default_factory=list)


class ApiLogOut(ORMModel):
    id: int
    correlation_id: str | None = None
    transaction_id: str | None = None
    source: str = "TRYIT"
    app_id: int | None = None
    app_name: str | None = None
    participant_id: int | None = None
    participant_name: str | None = None
    entity_id: str | None = None
    product_id: int | None = None
    endpoint_id: int | None = None
    environment: str | None = None
    method: str | None = None
    endpoint_url: str | None = None
    target_url: str | None = None
    status_code: int | None = None
    error_message: str | None = None
    latency_ms: float | None = None
    client_ip: str | None = None
    request_time: datetime | None = None
    response_time: datetime | None = None
    log_timestamp: datetime | None = None


class ApiLogDetailOut(ApiLogOut):
    upstream_latency_ms: float | None = None
    request_size: int | None = None
    response_size: int | None = None
    request_headers: dict[str, Any] | None = None
    request_body: Any = None
    response_body: Any = None


class UserActionLogQuery(ListQuery):
    actor_type: str | None = None
    actor_id: str | None = None
    action: str | None = None
    entity: str | None = None
    country_code: str | None = None
    date_from: date | None = None
    date_to: date | None = None


class UserActionLogOut(ORMModel):
    id: int
    actor_type: str
    actor_id: str | None = None
    actor_name: str | None = None
    action: str
    entity: str | None = None
    entity_id: str | None = None
    description: str | None = None
    ip_address: str | None = None
    correlation_id: str | None = None
    changes: dict[str, Any] | None = None
    timestamp: datetime | None = None


class ExportRequest(BaseModel):
    """Ask for the current grid as a spreadsheet rather than a page of rows."""

    format: str = Field("xlsx", pattern="^(xlsx|csv)$")
    filters: dict[str, Any] = Field(default_factory=dict)
