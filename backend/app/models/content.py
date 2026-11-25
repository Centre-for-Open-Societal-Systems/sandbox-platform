"""CMS content: FAQs, terms & conditions, email templates, home page blocks.

Every row carries a ``locale`` so a member country can publish the same entry in
English and its national languages (Amharic, Afaan Oromo, Tigrinya for
Ethiopia) without duplicating the table.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONB, AuditMixin, BigIntPk, SoftDeleteMixin, UniqueIdMixin


class FaqType(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "faq_type"

    type_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    faq_type: Mapped[str] = mapped_column(String(150), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(10), default="en", index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)

    details: Mapped[list[FaqDetail]] = relationship(
        back_populates="type", cascade="all, delete-orphan"
    )


class FaqDetail(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "faq_detail"

    faq_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_id: Mapped[int] = mapped_column(
        ForeignKey("faq_type.type_id"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(String(1000), nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(10), default="en", index=True)

    type: Mapped[FaqType] = relationship(back_populates="details")


class TermCondition(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "term_condition"

    table_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    sidebar_title: Mapped[str] = mapped_column(String(500), nullable=False)
    term_content: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(BigInteger, default=0)
    locale: Mapped[str] = mapped_column(String(10), default="en", index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)


class EmailTemplate(Base, AuditMixin):
    __tablename__ = "email_template"

    template_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    #: Machine key the services look up, e.g. "USER_APPROVED".
    template_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    template_name: Mapped[str] = mapped_column(String(150), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500))
    body_text: Mapped[str | None] = mapped_column(Text)
    #: Placeholder names the body accepts, e.g. ["name", "portal_url"].
    variables: Mapped[list | None] = mapped_column(JSONB, default=list)
    locale: Mapped[str] = mapped_column(String(10), default="en", index=True)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class HomePageBlock(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    """Editable blocks on the public landing page (hero, stats, sections)."""

    __tablename__ = "home_page_block"

    block_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    block_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    subtitle: Mapped[str | None] = mapped_column(String(1000))
    body: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(1000))
    #: Block-specific structured payload (counters, card lists, CTAs).
    content: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String(10), default="en", index=True)
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
