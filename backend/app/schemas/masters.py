"""Schemas for the lookup tables and geography."""

from __future__ import annotations

from datetime import datetime

from fastapi import UploadFile
from pydantic import BaseModel, Field

from app.schemas.common import ListQuery, ORMModel


# ------------------------------------------------------------------ lookups
class LookupCreate(BaseModel):
    """One shape for every lookup table - the service supplies the target."""

    name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0
    country_code: str | None = Field(None, max_length=2)
    #: Only used by SubCategory.
    parent_id: int | None = None
    #: Only used by ParticipantType.
    code: str | None = Field(None, max_length=20)


class LookupUpdate(LookupCreate):
    id: int = Field(..., ge=1)
    name: str | None = Field(None, min_length=1, max_length=100)


class LookupOut(ORMModel):
    id: int
    name: str
    sort_order: int = 0
    country_code: str | None = None
    parent_id: int | None = None
    code: str | None = None
    is_enabled: bool = True
    added_date: datetime | None = None


class LookupListQuery(ListQuery):
    country_code: str | None = None
    parent_id: int | None = None
    is_enabled: bool | None = None


class ProductCategoryCreate(BaseModel):
    category_name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    icon_path: str | None = None
    sort_order: int = 0
    country_code: str | None = Field(None, max_length=2)


class ProductCategoryUpdate(ProductCategoryCreate):
    category_id: int = Field(..., ge=1)
    category_name: str | None = Field(None, min_length=1, max_length=100)


class ProductCategoryOut(ORMModel):
    category_id: int
    category_name: str
    description: str | None = None
    icon_path: str | None = None
    sort_order: int = 0
    country_code: str | None = None
    is_enabled: bool = True
    product_count: int = 0


class ProductCategoryCreateForm(ProductCategoryCreate):
    """Multipart variant carrying the category icon."""

    icon: UploadFile | None = None


class ProductCategoryUpdateForm(ProductCategoryUpdate):
    icon: UploadFile | None = None


# ---------------------------------------------------------------- geography
class CountryCreate(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    country_code3: str | None = Field(None, min_length=3, max_length=3)
    country_name: str = Field(..., min_length=2, max_length=100)
    currency_code: str | None = Field(None, max_length=3)
    dial_code: str | None = Field(None, max_length=8)
    default_locale: str = "en"
    supported_locales: list[str] = Field(default_factory=lambda: ["en"])
    #: Tier display names keyed by level, e.g. {"1": "Region", "2": "Zone"}.
    level_labels: dict[str, str] = Field(default_factory=dict)
    level_depth: int = Field(4, ge=1, le=4)
    is_live: bool = False


class CountryUpdate(CountryCreate):
    country_name: str | None = Field(None, min_length=2, max_length=100)


class CountryOut(ORMModel):
    country_id: int
    country_code: str
    country_code3: str | None = None
    country_name: str
    currency_code: str | None = None
    dial_code: str | None = None
    default_locale: str = "en"
    supported_locales: list[str] | None = None
    level_labels: dict[str, str] | None = None
    level_depth: int = 4
    is_live: bool = False
    is_enabled: bool = True


class AdminAreaCreate(BaseModel):
    country_code: str = Field(..., min_length=2, max_length=2)
    area_code: str = Field(..., min_length=1, max_length=20)
    area_name: str = Field(..., min_length=1, max_length=255)
    area_name_local: str | None = Field(None, max_length=255)
    level: int = Field(..., ge=1, le=4)
    parent_id: int | None = None
    latitude: str | None = None
    longitude: str | None = None
    is_api_data_enabled: bool = False


class AdminAreaUpdate(AdminAreaCreate):
    area_id: int = Field(..., ge=1)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    area_code: str | None = Field(None, min_length=1, max_length=20)
    area_name: str | None = Field(None, min_length=1, max_length=255)
    level: int | None = Field(None, ge=1, le=4)


class AdminAreaOut(ORMModel):
    area_id: int
    country_code: str
    area_code: str
    area_name: str
    area_name_local: str | None = None
    level: int
    #: Display name for this tier, resolved from the country's level_labels.
    level_label: str | None = None
    parent_id: int | None = None
    path: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    is_api_data_enabled: bool = False
    is_enabled: bool = True
    child_count: int = 0


class AdminAreaTreeNode(AdminAreaOut):
    children: list[AdminAreaTreeNode] = Field(default_factory=list)


class AreaQuery(BaseModel):
    country_code: str | None = None
    level: int | None = Field(None, ge=1, le=4)
    parent_id: int | None = None
    parent_code: str | None = None
    search: str | None = None
    only_enabled: bool = True


class DropdownQuery(BaseModel):
    country_code: str | None = None
    parent_id: int | None = None
    only_enabled: bool = True


AdminAreaTreeNode.model_rebuild()
