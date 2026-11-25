"""Request/response building blocks shared across modules."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for read models projected straight off SQLAlchemy rows."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SealedPayload(BaseModel):
    """Envelope for RSA-sealed request bodies.

    The browser encrypts sensitive form data (credentials in particular) before
    transit and posts it as a single ``post_data`` string. See
    ``core.security.rsa_decrypt_payload``.
    """

    post_data: str = Field(..., description="RSA-sealed JSON payload")


class ListQuery(BaseModel):
    """Standard list envelope every admin grid posts."""

    page: int = Field(1, ge=1)
    limit: int = Field(10, ge=1, le=200)
    search: str | None = None
    sort_by: str | None = None
    sort_dir: str = Field("desc", pattern="^(?i)(asc|desc)$")
    filters: dict[str, Any] = Field(default_factory=dict)


class IdRequest(BaseModel):
    id: int = Field(..., ge=1)


class UniqueIdRequest(BaseModel):
    unique_id: str


class ToggleRequest(BaseModel):
    id: int = Field(..., ge=1)
    is_enabled: bool | None = None


class Pagination(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int


class PagedResult(BaseModel, Generic[T]):
    rows: list[T]
    pagination: Pagination


class DropdownItem(BaseModel):
    """Uniform ``{label, value}`` pair for every select in the UI."""

    label: str
    value: int | str
    extra: dict[str, Any] | None = None


class Envelope(BaseModel, Generic[T]):
    """Documents the wire format produced by ``core.responses``.

    Used for OpenAPI response models only - the handlers return the plain
    dict so the shape stays identical to the reference service.
    """

    message: str
    status: bool
    code: int
    data: T | None = None
