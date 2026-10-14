"""Generic CRUD repository.

Repositories own persistence only - no HTTP concerns, no business rules. That
keeps services testable against a plain session and makes the swap from the
reference Sequelize models a mechanical one.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.pagination import Page, apply_search, apply_sort, paginate

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    #: Concrete subclasses set these two.
    model: type[ModelT]
    pk_name: str

    #: Columns a free-text search scans, and the default sort column.
    search_columns: Sequence[str] = ()
    default_sort: str = "added_date"

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------- helpers
    @property
    def pk(self):
        return getattr(self.model, self.pk_name)

    def base_stmt(self, include_deleted: bool = False) -> Select:
        stmt = select(self.model)
        if not include_deleted and hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        return stmt

    def search_cols(self):
        return [
            getattr(self.model, c)
            for c in self.search_columns
            if hasattr(self.model, c)
        ]

    # ---------------------------------------------------------------- read
    def get(self, entity_id: Any, include_deleted: bool = False) -> ModelT | None:
        stmt = self.base_stmt(include_deleted).where(self.pk == entity_id)
        return self.db.execute(stmt).scalars().first()

    def get_many(self, entity_ids: Any, include_deleted: bool = True) -> list[ModelT]:
        """Fetch several rows by primary key in one query (deleted rows included)."""
        ids = list(entity_ids)
        if not ids:
            return []
        stmt = self.base_stmt(include_deleted).where(self.pk.in_(ids))
        return list(self.db.execute(stmt).scalars().all())

    def get_by(self, include_deleted: bool = False, **filters: Any) -> ModelT | None:
        stmt = self.base_stmt(include_deleted)
        for key, value in filters.items():
            stmt = stmt.where(getattr(self.model, key) == value)
        return self.db.execute(stmt).scalars().first()

    def get_by_unique_id(self, unique_id: str) -> ModelT | None:
        return self.get_by(unique_id=unique_id)

    def exists(self, **filters: Any) -> bool:
        return self.get_by(**filters) is not None

    def list_all(
        self,
        include_deleted: bool = False,
        only_enabled: bool = False,
        order_by: str | None = None,
        **filters: Any,
    ) -> list[ModelT]:
        stmt = self.base_stmt(include_deleted)
        if only_enabled and hasattr(self.model, "is_enabled"):
            stmt = stmt.where(self.model.is_enabled.is_(True))
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        column = getattr(self.model, order_by or self.default_sort, None)
        if column is not None:
            stmt = stmt.order_by(column)
        return list(self.db.execute(stmt).scalars().all())

    def paginate(
        self,
        page: int | None = 1,
        limit: int | None = 10,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = "desc",
        stmt: Select | None = None,
        **filters: Any,
    ) -> Page:
        stmt = self.base_stmt() if stmt is None else stmt
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        stmt = apply_search(stmt, search, self.search_cols())
        stmt = apply_sort(stmt, self.model, sort_by, sort_dir, self.default_sort)
        return paginate(self.db, stmt, page, limit)

    def count(self, **filters: Any) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(self.model)
        if hasattr(self.model, "is_deleted"):
            stmt = stmt.where(self.model.is_deleted.is_(False))
        for key, value in filters.items():
            if value is not None and hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
        return int(self.db.execute(stmt).scalar_one())

    # --------------------------------------------------------------- write
    def create(self, commit: bool = True, **values: Any) -> ModelT:
        entity = self.model(**values)
        self.db.add(entity)
        self._flush(commit, entity)
        return entity

    def update(self, entity: ModelT, commit: bool = True, **values: Any) -> ModelT:
        for key, value in values.items():
            if value is not None and hasattr(entity, key):
                setattr(entity, key, value)
        self._flush(commit, entity)
        return entity

    def set_fields(self, entity: ModelT, commit: bool = True, **values: Any) -> ModelT:
        """Like ``update`` but writes ``None`` through, for clearing fields."""
        for key, value in values.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        self._flush(commit, entity)
        return entity

    def soft_delete(self, entity: ModelT, actor_id: int | None = None) -> ModelT:
        if hasattr(entity, "is_deleted"):
            entity.is_deleted = True
        if hasattr(entity, "is_enabled"):
            entity.is_enabled = False
        if actor_id is not None and hasattr(entity, "modify_by"):
            entity.modify_by = actor_id
        self._flush(True, entity)
        return entity

    def toggle(
        self, entity: ModelT, value: bool | None = None, actor_id: int | None = None
    ) -> ModelT:
        current = bool(getattr(entity, "is_enabled", True))
        entity.is_enabled = (not current) if value is None else value
        if actor_id is not None and hasattr(entity, "modify_by"):
            entity.modify_by = actor_id
        self._flush(True, entity)
        return entity

    def hard_delete(self, entity: ModelT) -> None:
        self.db.delete(entity)
        self.db.commit()

    def bulk_create(
        self, rows: list[dict[str, Any]], commit: bool = True
    ) -> list[ModelT]:
        entities = [self.model(**row) for row in rows]
        self.db.add_all(entities)
        if commit:
            self.db.commit()
            for entity in entities:
                self.db.refresh(entity)
        else:
            self.db.flush()
        return entities

    def _flush(self, commit: bool, entity: ModelT) -> None:
        if commit:
            self.db.commit()
            self.db.refresh(entity)
        else:
            self.db.flush()
