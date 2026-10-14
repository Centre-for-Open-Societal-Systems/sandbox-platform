"""The API catalogue: products, endpoints, request/response schemas, mappers.

Ports ``product`` / ``endpoint`` / ``endpoints_schema`` / ``mapper_data``.
A *product* is a published bundle (e.g. "Farmer Registry"); an *endpoint* is a
single operation inside it; an *endpoint schema* pins one status-code variant
of that operation's request and response, which is what the sandbox
"try it" console validates against.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONB, AuditMixin, BigIntPk, SoftDeleteMixin, UniqueIdMixin
from app.models.enums import ApiType


class Product(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "product"

    product_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    product_name: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    page_text: Mapped[str | None] = mapped_column(Text)
    key_features: Mapped[str | None] = mapped_column(Text)
    product_note: Mapped[str | None] = mapped_column(String(1000))

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_category.category_id"), index=True
    )
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)

    #: Assets - relative paths resolved by the storage service.
    product_icon: Mapped[str | None] = mapped_column(String(1000))
    flow_chart: Mapped[str | None] = mapped_column(String(1000))
    product_documentation_pdf: Mapped[str | None] = mapped_column(String(1000))

    #: OpenAPI spec: raw text plus the parsed form used to derive endpoints.
    open_spec: Mapped[str | None] = mapped_column(Text)
    open_spec_json: Mapped[dict | None] = mapped_column(JSONB)
    api_doc_version: Mapped[str | None] = mapped_column(String(20))

    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    #: Published to the upstream gateway (distinct from visible in the portal).
    is_gateway_published: Mapped[bool] = mapped_column(Boolean, default=False)
    #: True when authored by hand rather than imported from a spec.
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    is_routing_applicable: Mapped[bool] = mapped_column(Boolean, default=False)

    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)
    meta_key: Mapped[str | None] = mapped_column(String(1000))
    meta_desc: Mapped[str | None] = mapped_column(String(1000))
    product_keywords: Mapped[list | None] = mapped_column(JSONB, default=list)

    #: Gateway-side identity and credentials.
    gateway_product_id: Mapped[str | None] = mapped_column(String(255))
    api_key: Mapped[str | None] = mapped_column(String(1000))
    api_secret: Mapped[str | None] = mapped_column(String(1000))
    key_issued_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    key_expiry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    endpoints: Mapped[list[Endpoint]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class Endpoint(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "endpoint"

    endpoint_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("product.product_id"), nullable=False, index=True
    )

    display_name: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    endpoint_url: Mapped[str | None] = mapped_column(String(2000))
    #: Per-environment upstreams the sandbox proxy forwards to.
    sandbox_api_url: Mapped[str | None] = mapped_column(String(2000))
    uat_api_url: Mapped[str | None] = mapped_column(String(2000))
    prod_api_url: Mapped[str | None] = mapped_column(String(2000))
    redirect_url: Mapped[str | None] = mapped_column(String(2000))

    method: Mapped[str | None] = mapped_column(String(10))
    path_params: Mapped[dict | None] = mapped_column(JSONB)
    query_params: Mapped[dict | None] = mapped_column(JSONB)
    header_params: Mapped[dict | None] = mapped_column(JSONB)
    request_schema: Mapped[dict | None] = mapped_column(JSONB)
    request_sample: Mapped[dict | None] = mapped_column(JSONB)

    api_type: Mapped[str] = mapped_column(
        String(20), default=str(ApiType.NATIONAL), index=True
    )
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    #: Endpoint only answers for a specific administrative area.
    area_scoped: Mapped[bool] = mapped_column(Boolean, default=False)

    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_gateway_published: Mapped[bool] = mapped_column(Boolean, default=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)
    api_keywords: Mapped[list | None] = mapped_column(JSONB, default=list)
    documentation_pdf: Mapped[str | None] = mapped_column(String(1000))

    #: Field-level transformation applied between provider and consumer.
    has_mapper: Mapped[bool] = mapped_column(Boolean, default=False)
    mapper_id: Mapped[int | None] = mapped_column(
        ForeignKey("mapper_data.mapper_id"), index=True
    )
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    category_ids: Mapped[list | None] = mapped_column(JSONB, default=list)

    #: Set when a provider (AIP) registered the endpoint rather than an admin.
    provider_participant_id: Mapped[int | None] = mapped_column(BigInteger, index=True)

    product: Mapped[Product] = relationship(back_populates="endpoints")
    schemas: Mapped[list[EndpointSchema]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )
    mapper: Mapped[MapperData | None] = relationship(back_populates="endpoints")


class EndpointSchema(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    """One status-code variant of an endpoint's contract."""

    __tablename__ = "endpoint_schema"

    schema_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("endpoint.endpoint_id"), nullable=False, index=True
    )
    product_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    status_code: Mapped[str] = mapped_column(String(10), default="200")

    header_json: Mapped[dict | None] = mapped_column(JSONB)
    path_params: Mapped[dict | None] = mapped_column(JSONB)
    req_schema: Mapped[dict | None] = mapped_column(JSONB)
    req_json: Mapped[dict | None] = mapped_column(JSONB)
    res_schema: Mapped[dict | None] = mapped_column(JSONB)
    res_json: Mapped[dict | None] = mapped_column(JSONB)

    req_schema_updated: Mapped[bool] = mapped_column(Boolean, default=False)
    res_schema_updated: Mapped[bool] = mapped_column(Boolean, default=False)
    provider_participant_id: Mapped[int | None] = mapped_column(BigInteger)

    endpoint: Mapped[Endpoint] = relationship(back_populates="schemas")


class MapperData(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    """Named input->output field mapping shared by endpoints of a use case."""

    __tablename__ = "mapper_data"

    mapper_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    usecase_name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    input_schema_id: Mapped[str | None] = mapped_column(String(50))
    output_schema_id: Mapped[str | None] = mapped_column(String(50))
    #: ``[{"source": "farmerName", "target": "full_name", "transform": null}]``
    field_map: Mapped[list | None] = mapped_column(JSONB, default=list)
    provider_participant_id: Mapped[int | None] = mapped_column(BigInteger)

    endpoints: Mapped[list[Endpoint]] = relationship(back_populates="mapper")
