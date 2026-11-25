"""API usage and billing report for the admin console.

Counts calls from ``api_log`` (try-it and direct app-key calls alike) per
partner, partner + API, API, app, product, day or status code. Country
administrators only ever see their own country's partners.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.context import admin_country_scope
from app.core.pagination import Page, normalise
from app.models.catalog import Product
from app.models.logs import ApiLog
from app.repositories.log_repository import USAGE_GROUPS, ApiLogRepository
from app.schemas.content import (
    ApiUsageCount,
    ApiUsageQuery,
    ApiUsageRow,
    ApiUsageSummary,
    UsageLookupQuery,
)
from app.utils import exporters

#: Rows written to a single spreadsheet export.
EXPORT_ROW_LIMIT = 5000
#: Longest date range the daily trend is zero-filled for.
MAX_FILLED_DAYS = 366

#: Sort keys the grid may ask for -> the report column they order by.
_SORT_COLUMNS = {
    "participant_name": "company_name",
    "app_name": "app_name",
    "product_name": "product_name",
    "endpoint_url": "endpoint_url",
    "day": "day",
    "status_code": "status_code",
    "total_calls": "total_calls",
    "success_calls": "success_calls",
    "client_errors": "client_errors",
    "server_errors": "server_errors",
    "avg_latency_ms": "avg_latency_ms",
    "first_call": "first_call",
    "last_call": "last_call",
}

_IDENTITY_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "participant": [("participant_name", "Partner"), ("email_id", "Email"), ("country_code", "Country"),
                    ("apps_used", "Apps"), ("endpoints_used", "APIs used")],
    "participant_endpoint": [("participant_name", "Partner"), ("email_id", "Email"), ("product_name", "Product"),
                             ("method", "Method"), ("endpoint_url", "End-point")],
    "endpoint": [("product_name", "Product"), ("method", "Method"), ("endpoint_url", "End-point")],
    "app": [("participant_name", "Partner"), ("app_name", "App"), ("endpoints_used", "APIs used")],
    "product": [("product_name", "Product"), ("endpoints_used", "APIs used")],
    "day": [("day", "Date")],
    "status": [("status_code", "Status code")],
}
_COUNT_COLUMNS = [
    ("total_calls", "Total calls"),
    ("success_calls", "Successful (2xx/3xx)"),
    ("client_errors", "Client errors (4xx)"),
    ("server_errors", "Server errors (5xx / no answer)"),
    ("success_rate", "Success rate %"),
    ("avg_latency_ms", "Avg latency (ms)"),
    ("first_call", "First call"),
    ("last_call", "Last call"),
]


def _filters(query: ApiUsageQuery) -> dict[str, Any]:
    """Query filters, with the country pinned for country administrators."""
    filters = query.model_dump()
    if (scope := admin_country_scope()) is not None:
        filters["country_code"] = scope
    return filters


def _rate(part: int | None, total: int | None) -> float | None:
    return round(100 * (part or 0) / total, 1) if total else None


def _participant_name(row: Any) -> str | None:
    company = getattr(row, "company_name", None)
    person = " ".join(
        part for part in (getattr(row, "first_name", None), getattr(row, "last_name", None)) if part
    )
    return company or person or getattr(row, "email_id", None)


def _to_row(row: Any) -> ApiUsageRow:
    values = {key: value for key, value in row._mapping.items() if key in ApiUsageRow.model_fields}
    latency = values.get("avg_latency_ms")
    values.update(
        participant_name=_participant_name(row) if "participant_id" in values else None,
        avg_latency_ms=round(float(latency), 1) if latency is not None else None,
        success_rate=_rate(values.get("success_calls"), values.get("total_calls")),
    )
    return ApiUsageRow(**values)


def _sorted_usage_stmt(db: Session, query: ApiUsageQuery) -> Select:
    stmt = ApiLogRepository(db).usage_stmt(query.group_by, _filters(query), query.search)
    columns = stmt.selected_columns
    sort_key = _SORT_COLUMNS.get(query.sort_by or "", "total_calls")
    if sort_key not in columns:
        sort_key = "total_calls"
    sort_column = columns[sort_key]
    descending = (query.sort_dir or "desc").lower() == "desc"
    tie_break = [columns[key] for key in USAGE_GROUPS[query.group_by]]
    return stmt.order_by(sort_column.desc() if descending else sort_column.asc(), *tie_break)


def list_usage(db: Session, query: ApiUsageQuery) -> Page:
    stmt = _sorted_usage_stmt(db, query)
    page, limit = normalise(query.page, query.limit)
    total = db.execute(select(func.count()).select_from(stmt.order_by(None).subquery())).scalar_one()
    rows = db.execute(stmt.offset((page - 1) * limit).limit(limit)).all()
    return Page(rows=[_to_row(row) for row in rows], total=int(total), page=page, limit=limit)


def usage_summary(db: Session, query: ApiUsageQuery) -> ApiUsageSummary:
    repo = ApiLogRepository(db)
    filters = _filters(query)
    totals = repo.usage_totals(filters)

    def counts(column: str) -> list[ApiUsageCount]:
        return [
            ApiUsageCount(label=str(label) if label is not None else "No answer", value=int(value))
            for label, value in repo.usage_breakdown(column, filters)
        ]

    return ApiUsageSummary(
        total_calls=int(totals.total_calls or 0),
        success_calls=int(totals.success_calls or 0),
        client_errors=int(totals.client_errors or 0),
        server_errors=int(totals.server_errors or 0),
        success_rate=_rate(totals.success_calls, totals.total_calls),
        avg_latency_ms=round(float(totals.avg_latency_ms), 1)
        if totals.avg_latency_ms is not None
        else None,
        partners=int(totals.partners or 0),
        apps=int(totals.apps or 0),
        endpoints=int(totals.endpoints or 0),
        first_call=totals.first_call,
        last_call=totals.last_call,
        by_status_code=counts("status_code"),
        by_source=counts("source"),
        by_day=_fill_days(counts("day"), query.date_from, query.date_to),
    )


def _fill_days(
    points: list[ApiUsageCount], date_from: date | None, date_to: date | None
) -> list[ApiUsageCount]:
    """Zero-fill quiet days inside a chosen date range so the trend has no gaps."""
    if not date_from or not date_to or date_to < date_from:
        return points
    days = (date_to - date_from).days
    if days > MAX_FILLED_DAYS:
        return points
    by_day = {point.label: point.value for point in points}
    return [
        ApiUsageCount(label=label, value=by_day.get(label, 0))
        for label in ((date_from + timedelta(days=offset)).isoformat() for offset in range(days + 1))
    ]


def usage_options(db: Session) -> dict[str, Any]:
    """Products that appear in the logs (a short list, so sent whole).

    Partners and apps can run to many thousands: they are searched and paged
    through ``lookup_partners`` / ``lookup_apps`` instead.
    """
    has_calls = select(ApiLog.id).where(ApiLog.product_id == Product.product_id).exists()
    products = [
        {"product_id": product_id, "name": display_name or product_name}
        for product_id, display_name, product_name in db.execute(
            select(Product.product_id, Product.display_name, Product.product_name)
            .where(has_calls)
            .order_by(Product.product_name)
        ).all()
    ]
    return {"products": products}


def _lookup_page(rows: list, query: UsageLookupQuery, to_item) -> dict[str, Any]:
    """Infinite-scroll page: one extra row fetched tells whether more exist (no COUNT)."""
    return {
        "rows": [to_item(row) for row in rows[: query.limit]],
        "page": query.page,
        "has_more": len(rows) > query.limit,
    }


def lookup_partners(db: Session, query: UsageLookupQuery) -> dict[str, Any]:
    rows = ApiLogRepository(db).usage_partners(
        query.search, (query.page - 1) * query.limit, query.limit + 1, admin_country_scope()
    )
    return _lookup_page(
        rows,
        query,
        lambda row: {
            "id": row.participant_id,
            "label": _participant_name(row) or f"Partner #{row.participant_id}",
            "hint": row.email_id,
        },
    )


def lookup_apps(db: Session, query: UsageLookupQuery) -> dict[str, Any]:
    rows = ApiLogRepository(db).usage_apps(
        query.search,
        (query.page - 1) * query.limit,
        query.limit + 1,
        query.participant_ids,
        admin_country_scope(),
    )
    return _lookup_page(
        rows,
        query,
        lambda row: {"id": row.app_id, "label": row.name, "hint": row.company_name or row.email_id},
    )


def export_usage(db: Session, query: ApiUsageQuery, fmt: str) -> tuple[bytes, str, str]:
    """The whole report (not just the page on screen), up to ``EXPORT_ROW_LIMIT`` rows."""
    stmt = _sorted_usage_stmt(db, query).limit(EXPORT_ROW_LIMIT)
    rows = [_to_row(row).model_dump() for row in db.execute(stmt).all()]
    columns = _IDENTITY_COLUMNS[query.group_by] + _COUNT_COLUMNS
    return exporters.export(rows, columns, fmt, "API Usage")
