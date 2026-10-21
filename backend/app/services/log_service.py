"""Audit-log and API-log queries, plus the admin dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.core.pagination import Page, apply_search, apply_sort, paginate
from app.models.logs import ApiLog, UserActionLog
from app.repositories.catalog_repository import EndpointRepository, ProductRepository
from app.repositories.log_repository import ApiLogRepository, UserActionLogRepository
from app.repositories.participant_repository import (
    ParticipantQueryRepository,
    ParticipantRepository,
)
from app.schemas.admin import (
    DashboardApiHealth,
    DashboardCounters,
    DashboardEndpointStat,
    DashboardResponse,
    DashboardSeriesPoint,
)
from app.schemas.content import (
    ApiLogDetailOut,
    ApiLogOut,
    ApiLogQuery,
    UserActionLogOut,
    UserActionLogQuery,
)
from app.utils import exporters

TREND_DAYS = 30
#: Rows written to a single spreadsheet export.
EXPORT_ROW_LIMIT = 5000


def list_api_logs(db: Session, query: ApiLogQuery) -> Page:
    repo = ApiLogRepository(db)
    stmt = repo.apply_filters(repo.base_stmt(), query.model_dump())
    stmt = apply_search(stmt, query.search, repo.search_cols())
    stmt = apply_sort(stmt, ApiLog, query.sort_by, query.sort_dir, repo.default_sort)

    page = paginate(db, stmt, query.page, query.limit)
    page.rows = [ApiLogOut.model_validate(row) for row in page.rows]
    return page


def get_api_log(db: Session, log_id: int) -> ApiLogDetailOut | None:
    row = ApiLogRepository(db).get(log_id)
    return ApiLogDetailOut.model_validate(row) if row else None


def list_user_action_logs(db: Session, query: UserActionLogQuery) -> Page:
    repo = UserActionLogRepository(db)
    stmt = repo.apply_filters(repo.base_stmt(), query.model_dump())
    stmt = apply_search(stmt, query.search, repo.search_cols())
    stmt = apply_sort(
        stmt, UserActionLog, query.sort_by, query.sort_dir, repo.default_sort
    )

    page = paginate(db, stmt, query.page, query.limit)
    page.rows = [UserActionLogOut.model_validate(row) for row in page.rows]
    return page


def export_api_logs(
    db: Session, query: ApiLogQuery, fmt: str
) -> tuple[bytes, str, str]:
    query.limit = EXPORT_ROW_LIMIT
    page = list_api_logs(db, query)
    rows = [row.model_dump() for row in page.rows]
    return exporters.export(rows, exporters.API_LOG_COLUMNS, fmt, "API Logs")


def export_user_action_logs(
    db: Session, query: UserActionLogQuery, fmt: str
) -> tuple[bytes, str, str]:
    query.limit = EXPORT_ROW_LIMIT
    page = list_user_action_logs(db, query)
    rows = [row.model_dump() for row in page.rows]
    return exporters.export(rows, exporters.USER_ACTION_COLUMNS, fmt, "User Tracking")


def dashboard(db: Session, country_code: str | None = None) -> DashboardResponse:
    users = ParticipantRepository(db)
    products = ProductRepository(db)
    api_logs = ApiLogRepository(db)

    total_products, published_products = products.counts()
    counters = DashboardCounters(
        **users.counts_by_status(country_code),
        total_products=total_products,
        published_products=published_products,
        total_endpoints=EndpointRepository(db).count(),
        api_calls_today=api_logs.count_today(),
        api_calls_month=api_logs.count_this_month(),
        open_queries=ParticipantQueryRepository(db).open_count(),
    )

    since = datetime.now(UTC) - timedelta(days=TREND_DAYS)
    health = api_logs.health_since(since)
    health["success_rate"] = _rate(health["success"], health["total_calls"])

    return DashboardResponse(
        counters=counters,
        trend_days=TREND_DAYS,
        registrations_trend=_to_series(
            users.registrations_by_month(country_code=country_code)
        ),
        api_usage_trend=_fill_days(
            _to_series(api_logs.usage_by_day(TREND_DAYS)), TREND_DAYS
        ),
        api_health=DashboardApiHealth(**health),
        top_endpoints=[
            DashboardEndpointStat(
                method=row.method,
                endpoint_url=row.endpoint_url,
                product_name=row.display_name or row.product_name,
                calls=int(row.calls),
                success_rate=_rate(row.success, row.calls),
                avg_latency_ms=round(float(row.avg_latency_ms), 1)
                if row.avg_latency_ms is not None
                else None,
            )
            for row in api_logs.endpoint_stats(since)
        ],
    )


def participant_dashboard(db: Session, participant_id: int) -> dict[str, Any]:
    api_logs = ApiLogRepository(db)
    since = datetime.now(UTC) - timedelta(days=TREND_DAYS)

    return {
        "api_calls_today": api_logs.count_today(participant_id),
        "api_calls_month": api_logs.count_this_month(participant_id),
        "api_calls_period": api_logs.count_since(since, participant_id),
        "usage_trend": [
            point.model_dump()
            for point in _to_series(api_logs.usage_by_day(TREND_DAYS, participant_id))
        ],
        "top_endpoints": [
            point.model_dump()
            for point in _to_series(
                api_logs.top_endpoints(participant_id=participant_id)
            )
        ],
    }


def _rate(part: int | None, total: int | None) -> float | None:
    return round(100 * (part or 0) / total, 1) if total else None


def _fill_days(points: list[DashboardSeriesPoint], days: int) -> list[DashboardSeriesPoint]:
    """One point per day (oldest first) so quiet days plot as zero, not a gap."""
    by_day = {point.label: point.value for point in points}
    today = datetime.now(UTC).date()
    labels = [(today - timedelta(days=offset)).isoformat() for offset in range(days, -1, -1)]
    return [DashboardSeriesPoint(label=label, value=by_day.get(label, 0)) for label in labels]


def _to_series(rows) -> list[DashboardSeriesPoint]:
    return [
        DashboardSeriesPoint(label=str(label or "Unknown"), value=int(value or 0))
        for label, value in rows
    ]
