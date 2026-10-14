"""Geography.

The reference stack hard-coded India's LGD hierarchy
(``state -> district -> sub_district -> village``). OAN serves many countries,
so the hierarchy is generic and each country names its own tiers:

======  =================  ===============  ==========
Level   Ethiopia           Kenya            Generic
======  =================  ===============  ==========
1       Region             County           admin_1
2       Zone               Sub-county       admin_2
3       Woreda             Ward             admin_3
4       Kebele             Village          admin_4
======  =================  ===============  ==========

``Country.level_labels`` carries the display names, so the UI can render
"Region" for Ethiopia and "County" for Kenya off the same tables.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONB, AuditMixin, SoftDeleteMixin


class Country(Base, AuditMixin, SoftDeleteMixin):
    __tablename__ = "country"

    country_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    #: ISO-3166 alpha-2, e.g. "ET". The tenant key used across the schema.
    country_code: Mapped[str] = mapped_column(
        String(2), unique=True, nullable=False, index=True
    )
    country_code3: Mapped[str | None] = mapped_column(String(3))
    country_name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(String(3))
    dial_code: Mapped[str | None] = mapped_column(String(8))
    default_locale: Mapped[str] = mapped_column(String(10), default="en")
    #: Locales this member country publishes content in, e.g. ["en", "am", "om"].
    supported_locales: Mapped[list | None] = mapped_column(JSONB, default=list)
    #: Display names for the four tiers, e.g.
    #: {"1": "Region", "2": "Zone", "3": "Woreda", "4": "Kebele"}
    level_labels: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    #: How many tiers this country actually uses (1-4).
    level_depth: Mapped[int] = mapped_column(Integer, default=4)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)

    areas: Mapped[list[AdminArea]] = relationship(back_populates="country")


class AdminArea(Base, AuditMixin, SoftDeleteMixin):
    """One node of a country's administrative tree, any level.

    A self-referencing tree keeps all four tiers in one table instead of the
    four parallel ``*_lgd_data`` tables the reference schema used.
    """

    __tablename__ = "admin_area"
    __table_args__ = (
        UniqueConstraint(
            "country_code", "area_code", name="uq_admin_area_country_code"
        ),
    )

    area_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country_code: Mapped[str] = mapped_column(
        ForeignKey("country.country_code"), nullable=False, index=True
    )
    #: Official national code for this area (Ethiopia: CSA code).
    area_code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    area_name: Mapped[str] = mapped_column(String(255), nullable=False)
    area_name_local: Mapped[str | None] = mapped_column(String(255))
    #: 1..4, interpreted through ``Country.level_labels``.
    level: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_area.area_id"), index=True
    )
    #: Denormalised "1.14.203" path - lets the UI load a subtree in one query.
    path: Mapped[str | None] = mapped_column(String(255), index=True)

    latitude: Mapped[str | None] = mapped_column(String(32))
    longitude: Mapped[str | None] = mapped_column(String(32))
    #: Whether sandbox APIs expose data for this area.
    is_api_data_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    country: Mapped[Country] = relationship(back_populates="areas")
    parent: Mapped[AdminArea | None] = relationship(
        remote_side=[area_id], back_populates="children"
    )
    children: Mapped[list[AdminArea]] = relationship(back_populates="parent")
