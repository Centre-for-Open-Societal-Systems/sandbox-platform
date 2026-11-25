"""Persistence for lookup tables and geography.

Every lookup table has the same shape but different column names, so
``LookupRepository`` is parameterised by a small descriptor instead of being
copy-pasted eleven times.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.geo import AdminArea, Country
from app.models.masters import (
    Category,
    OperatingArea,
    ParticipantType,
    ProductCategory,
    ServiceDomain,
    SubCategory,
)
from app.repositories.base import BaseRepository


@dataclass(frozen=True)
class LookupSpec:
    """Maps a lookup table's own column names onto the generic API shape."""

    model: type
    pk: str
    name_column: str
    #: FK to the parent lookup, where the table has one (SubCategory only).
    parent_column: str | None = None


#: Keys are the ``kind`` path segment used by the generic master endpoints.
LOOKUPS: dict[str, LookupSpec] = {
    "participant-type": LookupSpec(
        ParticipantType, "participant_type_id", "participant_type_name"
    ),
    "service-domain": LookupSpec(
        ServiceDomain, "service_domain_id", "service_domain_name"
    ),
    "operating-area": LookupSpec(
        OperatingArea, "operating_area_id", "operating_area_name"
    ),
    "category": LookupSpec(Category, "category_id", "category_name"),
    "sub-category": LookupSpec(
        SubCategory, "sub_category_id", "sub_category_name", "category_id"
    ),
}


def resolve_spec(kind: str) -> LookupSpec:
    spec = LOOKUPS.get(kind)
    if spec is None:
        raise NotFoundError(f"Unknown master list '{kind}'.")
    return spec


class LookupRepository:
    """CRUD over any table registered in ``LOOKUPS``."""

    def __init__(self, db: Session, kind: str):
        self.db = db
        self.kind = kind
        self.spec = resolve_spec(kind)
        self.model = self.spec.model

    @property
    def pk(self):
        return getattr(self.model, self.spec.pk)

    @property
    def name_col(self):
        return getattr(self.model, self.spec.name_column)

    def _base(self) -> Select:
        return select(self.model).where(self.model.is_deleted.is_(False))

    def get(self, entity_id: int):
        return (
            self.db.execute(self._base().where(self.pk == entity_id)).scalars().first()
        )

    def get_or_404(self, entity_id: int):
        row = self.get(entity_id)
        if row is None:
            raise NotFoundError("Record not found.")
        return row

    def name_taken(
        self, name: str, exclude_id: int | None = None, parent_id: int | None = None
    ) -> bool:
        stmt = self._base().where(
            func.lower(self.name_col) == (name or "").strip().lower()
        )
        if exclude_id:
            stmt = stmt.where(self.pk != exclude_id)
        if self.spec.parent_column and parent_id is not None:
            stmt = stmt.where(getattr(self.model, self.spec.parent_column) == parent_id)
        return self.db.execute(stmt).scalars().first() is not None

    def list_rows(
        self,
        only_enabled: bool = True,
        country_code: str | None = None,
        parent_id: int | None = None,
        search: str | None = None,
    ) -> list[Any]:
        stmt = self._base()
        if only_enabled:
            stmt = stmt.where(self.model.is_enabled.is_(True))
        if country_code and hasattr(self.model, "country_code"):
            # NULL country_code rows are network-wide and always visible.
            stmt = stmt.where(
                or_(
                    self.model.country_code == country_code,
                    self.model.country_code.is_(None),
                )
            )
        if parent_id is not None and self.spec.parent_column:
            stmt = stmt.where(getattr(self.model, self.spec.parent_column) == parent_id)
        if search:
            stmt = stmt.where(
                func.lower(self.name_col).like(f"%{search.strip().lower()}%")
            )
        stmt = stmt.order_by(self.model.sort_order, self.name_col)
        return list(self.db.execute(stmt).scalars().all())

    def to_dict(self, row: Any) -> dict[str, Any]:
        """Project a row onto the generic ``LookupOut`` shape."""
        return {
            "id": getattr(row, self.spec.pk),
            "name": getattr(row, self.spec.name_column),
            "sort_order": getattr(row, "sort_order", 0),
            "country_code": getattr(row, "country_code", None),
            "parent_id": (
                getattr(row, self.spec.parent_column)
                if self.spec.parent_column
                else None
            ),
            "code": getattr(row, "code", None),
            "is_enabled": getattr(row, "is_enabled", True),
            "added_date": getattr(row, "added_date", None),
        }

    def create(self, name: str, actor_id: int | None = None, **extra: Any):
        values: dict[str, Any] = {
            self.spec.name_column: name.strip(),
            "sort_order": extra.get("sort_order", 0),
            "added_by": actor_id,
            "modify_by": actor_id,
        }
        if hasattr(self.model, "country_code"):
            values["country_code"] = extra.get("country_code")
        if self.spec.parent_column:
            values[self.spec.parent_column] = extra.get("parent_id")
        if hasattr(self.model, "code") and extra.get("code"):
            values["code"] = extra["code"]
        row = self.model(**values)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def update(self, row: Any, actor_id: int | None = None, **values: Any):
        if values.get("name"):
            setattr(row, self.spec.name_column, values["name"].strip())
        if values.get("sort_order") is not None:
            row.sort_order = values["sort_order"]
        if "country_code" in values and hasattr(row, "country_code"):
            row.country_code = values["country_code"]
        if self.spec.parent_column and values.get("parent_id") is not None:
            setattr(row, self.spec.parent_column, values["parent_id"])
        if values.get("code") and hasattr(row, "code"):
            row.code = values["code"]
        row.modify_by = actor_id
        self.db.commit()
        self.db.refresh(row)
        return row

    def toggle(self, row: Any, value: bool | None = None, actor_id: int | None = None):
        row.is_enabled = (not row.is_enabled) if value is None else value
        row.modify_by = actor_id
        self.db.commit()
        return row

    def soft_delete(self, row: Any, actor_id: int | None = None):
        row.is_deleted = True
        row.is_enabled = False
        row.modify_by = actor_id
        self.db.commit()
        return row


class ProductCategoryRepository(BaseRepository[ProductCategory]):
    model = ProductCategory
    pk_name = "category_id"
    search_columns = ("category_name", "description")
    default_sort = "sort_order"


class CountryRepository(BaseRepository[Country]):
    model = Country
    pk_name = "country_id"
    search_columns = ("country_name", "country_code")
    default_sort = "country_name"

    def get_by_code(self, code: str) -> Country | None:
        return self.get_by(country_code=(code or "").upper())

    def live_countries(self) -> list[Country]:
        stmt = (
            self.base_stmt()
            .where(Country.is_enabled.is_(True))
            .order_by(Country.country_name)
        )
        return list(self.db.execute(stmt).scalars().all())

    def level_label(self, country_code: str, level: int) -> str:
        country = self.get_by_code(country_code)
        labels = (country.level_labels or {}) if country else {}
        return labels.get(str(level)) or f"Level {level}"


class AdminAreaRepository(BaseRepository[AdminArea]):
    model = AdminArea
    pk_name = "area_id"
    search_columns = ("area_name", "area_name_local", "area_code")
    default_sort = "area_name"

    def get_by_code(self, country_code: str, area_code: str) -> AdminArea | None:
        return self.get_by(
            country_code=(country_code or "").upper(), area_code=area_code
        )

    def children_of(
        self,
        parent_id: int | None,
        country_code: str | None = None,
        level: int | None = None,
    ):
        stmt = self.base_stmt().where(AdminArea.is_enabled.is_(True))
        stmt = stmt.where(
            AdminArea.parent_id == parent_id
            if parent_id
            else AdminArea.parent_id.is_(None)
        )
        if country_code:
            stmt = stmt.where(AdminArea.country_code == country_code.upper())
        if level:
            stmt = stmt.where(AdminArea.level == level)
        return list(self.db.execute(stmt.order_by(AdminArea.area_name)).scalars().all())

    def by_level(self, country_code: str, level: int, only_enabled: bool = True):
        stmt = self.base_stmt().where(
            AdminArea.country_code == country_code.upper(), AdminArea.level == level
        )
        if only_enabled:
            stmt = stmt.where(AdminArea.is_enabled.is_(True))
        return list(self.db.execute(stmt.order_by(AdminArea.area_name)).scalars().all())

    def child_counts(self, area_ids: list[int]) -> dict[int, int]:
        if not area_ids:
            return {}
        stmt = (
            select(AdminArea.parent_id, func.count())
            .where(AdminArea.parent_id.in_(area_ids), AdminArea.is_deleted.is_(False))
            .group_by(AdminArea.parent_id)
        )
        return {
            int(pid): int(count) for pid, count in self.db.execute(stmt).all() if pid
        }

    def compute_path(self, parent_id: int | None, area_id: int) -> str:
        """Materialised ancestor path, so a subtree loads in one indexed query."""
        if not parent_id:
            return str(area_id)
        parent = self.get(parent_id)
        prefix = (
            (parent.path if parent and parent.path else str(parent_id))
            if parent
            else ""
        )
        return f"{prefix}.{area_id}" if prefix else str(area_id)

    def subtree(self, area: AdminArea) -> list[AdminArea]:
        prefix = area.path or str(area.area_id)
        stmt = self.base_stmt().where(
            AdminArea.country_code == area.country_code,
            or_(AdminArea.path == prefix, AdminArea.path.like(f"{prefix}.%")),
        )
        return list(
            self.db.execute(stmt.order_by(AdminArea.level, AdminArea.area_name))
            .scalars()
            .all()
        )
