"""Lookup tables backing the registration form dropdowns.

All of these share the same shape in the reference schema (id, name, audit,
enable/delete flags), so they share one mixin here. ``country_code`` is
nullable: NULL means the row is network-wide, a value scopes it to one member
country that needs its own option list.
"""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import AuditMixin, BigIntPk, SoftDeleteMixin


class _LookupMixin(AuditMixin, SoftDeleteMixin):
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)


class ParticipantType(Base, _LookupMixin):
    """How a member participates in the network - AIP or AIU.

    Distinct from ``AdmRole``, which is a back-office permission role.
    """

    __tablename__ = "participant_type"
    participant_type_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    participant_type_name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str | None] = mapped_column(String(20), index=True)


class ServiceDomain(Base, _LookupMixin):
    __tablename__ = "service_domain"
    service_domain_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    service_domain_name: Mapped[str] = mapped_column(String(100), nullable=False)


class OperatingArea(Base, _LookupMixin):
    __tablename__ = "operating_area"
    operating_area_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    operating_area_name: Mapped[str] = mapped_column(String(100), nullable=False)


class Category(Base, _LookupMixin):
    """Business category shown on the signup form (two-level)."""

    __tablename__ = "category"
    category_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)

    sub_categories: Mapped[list[SubCategory]] = relationship(back_populates="category")


class SubCategory(Base, _LookupMixin):
    __tablename__ = "sub_category"
    sub_category_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    sub_category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.category_id"), nullable=False, index=True
    )

    category: Mapped[Category] = relationship(back_populates="sub_categories")


class ProductCategory(Base, _LookupMixin):
    """Grouping shown on the API catalogue (distinct from business Category)."""

    __tablename__ = "product_category"
    category_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    icon_path: Mapped[str | None] = mapped_column(String(500))
