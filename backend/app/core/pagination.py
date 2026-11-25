"""Server-side pagination, search and sort helpers.

Admin list screens all post the same envelope, so one helper covers them:

    {"page": 1, "limit": 10, "search": "", "sort_by": "added_date",
     "sort_dir": "desc", "filters": {...}}
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import ColumnProperty, Session

MAX_PAGE_SIZE = 200


@dataclass(slots=True)
class Page:
    rows: list[Any]
    total: int
    page: int
    limit: int

    @property
    def total_pages(self) -> int:
        return ceil(self.total / self.limit) if self.limit else 0

    def as_dict(self, key: str = "rows") -> dict[str, Any]:
        return {
            key: self.rows,
            "pagination": {
                "page": self.page,
                "limit": self.limit,
                "total": self.total,
                "total_pages": self.total_pages,
            },
        }


def normalise(page: int | None, limit: int | None) -> tuple[int, int]:
    page = max(1, page or 1)
    limit = min(MAX_PAGE_SIZE, max(1, limit or 10))
    return page, limit


def apply_search(stmt: Select, term: str | None, columns: Sequence[Any]) -> Select:
    """Case-insensitive OR-match of `term` across `columns`."""
    if not term or not columns:
        return stmt
    pattern = f"%{term.strip().lower()}%"
    return stmt.where(or_(*(func.lower(col).like(pattern) for col in columns)))


#: Columns a list may never be ordered by: sorting leaks their order (e.g.
#: password hashes or reset tokens) to whoever can see the list.
_UNSORTABLE = re.compile(r"pass|token|otp|secret|hash|(^|_)key(_|$)", re.IGNORECASE)


def _sort_column(model: Any, name: str | None):
    """The mapped column ``name`` of ``model``, or None (relationships, methods, secrets)."""
    if not name or _UNSORTABLE.search(name):
        return None
    attr = getattr(model, name, None)
    return attr if isinstance(getattr(attr, "property", None), ColumnProperty) else None


def apply_sort(
    stmt: Select, model: Any, sort_by: str | None, sort_dir: str | None, default: str
) -> Select:
    column = _sort_column(model, sort_by)
    if column is None:
        column = getattr(model, default, None)
    if column is None:
        return stmt
    descending = (sort_dir or "desc").lower() == "desc"
    return stmt.order_by(column.desc() if descending else column.asc())


def paginate(db: Session, stmt: Select, page: int | None, limit: int | None) -> Page:
    page, limit = normalise(page, limit)
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(stmt.offset((page - 1) * limit).limit(limit)).scalars().all()
    return Page(rows=list(rows), total=int(total), page=page, limit=limit)
