"""Persistence for CMS content."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from app.models.content import (
    EmailTemplate,
    FaqDetail,
    FaqType,
    HomePageBlock,
    TermCondition,
)
from app.repositories.base import BaseRepository


class FaqTypeRepository(BaseRepository[FaqType]):
    model = FaqType
    pk_name = "type_id"
    search_columns = ("faq_type",)
    default_sort = "sort_order"

    def published(
        self, locale: str = "en", country_code: str | None = None
    ) -> list[FaqType]:
        stmt = self.base_stmt().where(
            FaqType.is_enabled.is_(True), FaqType.locale == locale
        )
        if country_code:
            stmt = stmt.where(
                or_(
                    FaqType.country_code == country_code, FaqType.country_code.is_(None)
                )
            )
        return list(self.db.execute(stmt.order_by(FaqType.sort_order)).scalars().all())

    def faq_counts(self, type_ids: list[int]) -> dict[int, int]:
        if not type_ids:
            return {}
        stmt = (
            select(FaqDetail.type_id, func.count())
            .where(FaqDetail.type_id.in_(type_ids), FaqDetail.is_deleted.is_(False))
            .group_by(FaqDetail.type_id)
        )
        return {int(tid): int(count) for tid, count in self.db.execute(stmt).all()}


class FaqRepository(BaseRepository[FaqDetail]):
    model = FaqDetail
    pk_name = "faq_id"
    search_columns = ("question", "answer")
    default_sort = "sort_order"

    def for_type(self, type_id: int, only_enabled: bool = True) -> list[FaqDetail]:
        stmt = self.base_stmt().where(FaqDetail.type_id == type_id)
        if only_enabled:
            stmt = stmt.where(FaqDetail.is_enabled.is_(True))
        return list(
            self.db.execute(stmt.order_by(FaqDetail.sort_order)).scalars().all()
        )

    def type_names(self, type_ids: list[int]) -> dict[int, str]:
        ids = [t for t in type_ids if t]
        if not ids:
            return {}
        stmt = select(FaqType.type_id, FaqType.faq_type).where(FaqType.type_id.in_(ids))
        return {int(tid): name for tid, name in self.db.execute(stmt).all()}


class TermRepository(BaseRepository[TermCondition]):
    model = TermCondition
    pk_name = "table_id"
    search_columns = ("sidebar_title", "term_content")
    default_sort = "sort_order"

    def published(
        self, locale: str = "en", country_code: str | None = None
    ) -> list[TermCondition]:
        stmt = self.base_stmt().where(
            TermCondition.is_enabled.is_(True), TermCondition.locale == locale
        )
        if country_code:
            stmt = stmt.where(
                or_(
                    TermCondition.country_code == country_code,
                    TermCondition.country_code.is_(None),
                )
            )
        return list(
            self.db.execute(stmt.order_by(TermCondition.sort_order)).scalars().all()
        )


class EmailTemplateRepository(BaseRepository[EmailTemplate]):
    model = EmailTemplate
    pk_name = "template_id"
    search_columns = ("template_name", "template_code", "subject")
    default_sort = "sort_order"

    def base_stmt(self, include_deleted: bool = False):
        # EmailTemplate has no soft-delete column; override the default filter.
        return select(EmailTemplate)

    def get_by_code(
        self, template_code: str, locale: str = "en"
    ) -> EmailTemplate | None:
        stmt = select(EmailTemplate).where(
            EmailTemplate.template_code == template_code,
            EmailTemplate.locale == locale,
            EmailTemplate.is_enabled.is_(True),
        )
        row = self.db.execute(stmt).scalars().first()
        if row or locale == "en":
            return row
        # Fall back to English when a locale has no override for this template.
        return (
            self.db.execute(
                select(EmailTemplate).where(
                    EmailTemplate.template_code == template_code,
                    EmailTemplate.locale == "en",
                    EmailTemplate.is_enabled.is_(True),
                )
            )
            .scalars()
            .first()
        )


class HomeBlockRepository(BaseRepository[HomePageBlock]):
    model = HomePageBlock
    pk_name = "block_id"
    search_columns = ("block_key", "title")
    default_sort = "sort_order"

    def published(
        self, locale: str = "en", country_code: str | None = None
    ) -> list[HomePageBlock]:
        stmt = self.base_stmt().where(
            HomePageBlock.is_enabled.is_(True), HomePageBlock.locale == locale
        )
        if country_code:
            stmt = stmt.where(
                or_(
                    HomePageBlock.country_code == country_code,
                    HomePageBlock.country_code.is_(None),
                )
            )
        return list(
            self.db.execute(stmt.order_by(HomePageBlock.sort_order)).scalars().all()
        )

    def get_by_key(self, block_key: str, locale: str = "en") -> HomePageBlock | None:
        return self.get_by(block_key=block_key, locale=locale)
