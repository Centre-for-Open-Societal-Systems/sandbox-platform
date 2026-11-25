"""Schemas for products, endpoints, endpoint schemas, mappers and the sandbox
"try it" console.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator

from app.models.enums import ApiType, Environment, HttpMethod
from app.schemas.common import ListQuery, ORMModel


# ----------------------------------------------------------------- products
class ProductCreate(BaseModel):
    product_name: str = Field(..., min_length=2, max_length=250)
    display_name: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=8000)
    page_text: str | None = None
    key_features: str | None = None
    product_note: str | None = Field(None, max_length=1000)
    category_id: int | None = None
    country_code: str | None = Field(None, max_length=2)
    api_doc_version: str | None = Field(None, max_length=20)
    sort_order: int = 0
    meta_key: str | None = None
    meta_desc: str | None = None
    product_keywords: list[str] = Field(default_factory=list)
    is_manual: bool = False
    is_routing_applicable: bool = False
    #: Served through the API gateway: endpoints without their own upstream
    #: URL are called on the gateway proxy (see GATEWAY_* settings).
    is_gateway_published: bool = False


class ProductUpdate(ProductCreate):
    product_id: int = Field(..., ge=1)
    product_name: str | None = Field(None, min_length=2, max_length=250)


class ProductOut(ORMModel):
    product_id: int
    unique_id: str
    product_name: str
    display_name: str | None = None
    description: str | None = None
    product_note: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    country_code: str | None = None
    product_icon: str | None = None
    flow_chart: str | None = None
    product_documentation_pdf: str | None = None
    api_doc_version: str | None = None
    is_published: bool = False
    is_gateway_published: bool = False
    is_manual: bool = False
    sort_order: int = 0
    product_keywords: list[str] | None = None
    endpoint_count: int = 0
    added_date: datetime | None = None
    modify_date: datetime | None = None


class ProductDetailOut(ProductOut):
    page_text: str | None = None
    key_features: str | None = None
    meta_key: str | None = None
    meta_desc: str | None = None
    open_spec_json: dict[str, Any] | None = None
    endpoints: list[EndpointOut] = Field(default_factory=list)


class CatalogMenuEndpoint(BaseModel):
    """One line of the portal's API menu - just enough to render and link it."""

    endpoint_id: int
    display_name: str | None = None
    endpoint_url: str | None = None
    method: str | None = None
    api_type: str | None = None


class CatalogMenuProduct(BaseModel):
    product_id: int
    product_name: str
    display_name: str | None = None
    category_name: str | None = None
    endpoints: list[CatalogMenuEndpoint] = Field(default_factory=list)


class ProductListQuery(ListQuery):
    category_id: int | None = None
    country_code: str | None = None
    is_published: bool | None = None


class PublishRequest(BaseModel):
    id: int = Field(..., ge=1)
    is_published: bool


class ImportSpecRequest(BaseModel):
    """Import an OpenAPI document and derive endpoints from its paths."""

    product_id: int = Field(..., ge=1)
    #: Raw OpenAPI text (JSON or YAML). Ignored when ``spec_url`` is given.
    spec_text: str | None = None
    spec_url: str | None = None
    #: Replace existing endpoints instead of merging by method+path.
    replace_existing: bool = False


class GatewaySyncRequest(BaseModel):
    """Pull the gateway's routes into the catalogue (see GATEWAY_SYNC_ENABLED)."""

    #: Compute the report without saving anything.
    dry_run: bool = False
    #: Which gateway to read: PRODUCTION reads production's own (GATEWAY_PROD_ADMIN_URL).
    environment: Environment = Environment.UAT


# ---------------------------------------------------------------- endpoints
class EndpointCreate(BaseModel):
    product_id: int = Field(..., ge=1)
    display_name: str = Field(..., min_length=2, max_length=500)
    description: str | None = None
    endpoint_url: str = Field(..., min_length=1, max_length=2000)
    method: HttpMethod = HttpMethod.POST
    api_type: ApiType = ApiType.NATIONAL
    country_code: str | None = Field(None, max_length=2)
    area_scoped: bool = False

    uat_api_url: str | None = None
    prod_api_url: str | None = None
    redirect_url: str | None = None
    #: Call through the API gateway when no upstream URL is set.
    is_gateway_published: bool = False

    path_params: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    header_params: dict[str, Any] | None = None
    request_schema: dict[str, Any] | None = None
    request_sample: dict[str, Any] | None = None

    api_keywords: list[str] = Field(default_factory=list)
    category_ids: list[int] = Field(default_factory=list)
    has_mapper: bool = False
    mapper_id: int | None = None
    sort_order: int = 0

    @field_validator("endpoint_url")
    @classmethod
    def _leading_slash(cls, v: str) -> str:
        v = v.strip()
        return v if v.startswith(("/", "http://", "https://")) else f"/{v}"

    @field_validator("uat_api_url", "prod_api_url")
    @classmethod
    def _http_url(cls, v: str | None) -> str | None:
        """Upstream base URLs: plain http(s) only, no credentials in the URL."""
        if not v or not v.strip():
            return None
        v = v.strip()
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Use an http:// or https:// URL.")
        if parts.username or parts.password:
            raise ValueError("Do not put credentials in the URL.")
        return v


class EndpointUpdate(EndpointCreate):
    endpoint_id: int = Field(..., ge=1)
    product_id: int | None = Field(None, ge=1)
    display_name: str | None = Field(None, min_length=2, max_length=500)
    endpoint_url: str | None = Field(None, min_length=1, max_length=2000)


class EndpointOut(ORMModel):
    endpoint_id: int
    unique_id: str
    product_id: int
    product_name: str | None = None
    display_name: str | None = None
    description: str | None = None
    endpoint_url: str | None = None
    method: str | None = None
    api_type: str | None = None
    country_code: str | None = None
    area_scoped: bool = False
    is_published: bool = False
    is_gateway_published: bool = False
    has_mapper: bool = False
    mapper_id: int | None = None
    sort_order: int = 0
    api_keywords: list[str] | None = None
    added_date: datetime | None = None


class EndpointDetailOut(EndpointOut):
    uat_api_url: str | None = None
    prod_api_url: str | None = None
    #: Where a call really goes per environment (own URL, else the gateway);
    #: ``None`` means UAT answers from samples.
    resolved_upstreams: dict[str, str | None] = Field(default_factory=dict)
    path_params: dict[str, Any] | None = None
    query_params: dict[str, Any] | None = None
    header_params: dict[str, Any] | None = None
    request_schema: dict[str, Any] | None = None
    request_sample: dict[str, Any] | None = None
    schemas: list[EndpointSchemaOut] = Field(default_factory=list)


class EndpointListQuery(ListQuery):
    product_id: int | None = None
    api_type: ApiType | None = None
    country_code: str | None = None
    is_published: bool | None = None


# ---------------------------------------------------------- endpoint schema
class EndpointSchemaCreate(BaseModel):
    endpoint_id: int = Field(..., ge=1)
    status_code: str = Field("200", max_length=10)
    header_json: dict[str, Any] | None = None
    path_params: dict[str, Any] | None = None
    req_schema: dict[str, Any] | None = None
    #: Any JSON value: a response can be an array or a scalar, not only an object.
    req_json: Any = None
    res_schema: dict[str, Any] | None = None
    res_json: Any = None


class EndpointSchemaUpdate(EndpointSchemaCreate):
    schema_id: int = Field(..., ge=1)
    endpoint_id: int | None = Field(None, ge=1)


class EndpointSchemaOut(ORMModel):
    schema_id: int
    endpoint_id: int
    status_code: str
    header_json: dict[str, Any] | None = None
    path_params: dict[str, Any] | None = None
    req_schema: dict[str, Any] | None = None
    #: Any JSON value: a response can be an array or a scalar, not only an object.
    req_json: Any = None
    res_schema: dict[str, Any] | None = None
    res_json: Any = None
    is_enabled: bool = True
    added_date: datetime | None = None


class GenerateSchemaRequest(BaseModel):
    """Derive a JSON Schema from a sample document."""

    sample: dict[str, Any] | list[Any]


# ------------------------------------------------------------------ mappers
class MapperCreate(BaseModel):
    usecase_name: str = Field(..., min_length=2, max_length=150)
    description: str | None = None
    input_schema_id: str | None = None
    output_schema_id: str | None = None
    field_map: list[dict[str, Any]] = Field(default_factory=list)


class MapperUpdate(MapperCreate):
    mapper_id: int = Field(..., ge=1)
    usecase_name: str | None = Field(None, min_length=2, max_length=150)


class MapperOut(ORMModel):
    mapper_id: int
    usecase_name: str
    description: str | None = None
    input_schema_id: str | None = None
    output_schema_id: str | None = None
    field_map: list[dict[str, Any]] | None = None
    is_enabled: bool = True
    added_date: datetime | None = None


# --------------------------------------------------------- sandbox "try it"
class TryItRequest(BaseModel):
    """Execute one catalogue endpoint against the environment's upstream."""

    endpoint_id: int = Field(..., ge=1)
    environment: Environment = Environment.UAT
    path_params: dict[str, Any] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    #: Call as this app (``app_id`` from ``GET /participant/apps``): its API
    #: key is sent in the GATEWAY_APP_KEY_HEADER header.
    app_id: str | None = None


class TryItResponse(BaseModel):
    status_code: int
    #: Milliseconds spent on the upstream call.
    latency_ms: float
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None
    request_url: str
    #: Correlation id, so the call can be found again in API History.
    transaction_id: str
    error: str | None = None


class CurlConvertRequest(BaseModel):
    """Turn a pasted curl command into the structured try-it form."""

    curl_command: str = Field(..., min_length=4)


class CodeSampleRequest(BaseModel):
    endpoint_id: int = Field(..., ge=1)
    language: str = Field(
        "curl", pattern="^(curl|python|javascript|java|go|php|csharp)$"
    )
    environment: Environment = Environment.UAT
    #: The try-it form as it is now. Without it the snippet shows the
    #: endpoint's published sample.
    request: CodeSampleForm | None = None


class CodeSampleForm(BaseModel):
    """What the participant typed in the try-it console, so the snippet matches it."""

    path_params: dict[str, Any] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    #: False for a request without a body (e.g. GET); ``body`` is then ignored.
    has_body: bool = True
    body: Any = None
    #: Show the call as this app: its API key goes in the GATEWAY_APP_KEY_HEADER header.
    app_id: str | None = None


ProductDetailOut.model_rebuild()
EndpointDetailOut.model_rebuild()
