"""Audit-log and API-log queries, plus the admin dashboard aggregation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.context import admin_country_scope, assert_in_admin_scope
from app.core.pagination import Page, apply_search, apply_sort, paginate
from app.models.app import ParticipantApp
from app.models.logs import ApiLog, UserActionLog
from app.models.participant import Participant
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
DashboardPeriod = Literal["today", "week", "month"]
#: Rows written to a single spreadsheet export.
EXPORT_ROW_LIMIT = 5000


def _api_logs_stmt(db: Session, query: ApiLogQuery):
    repo = ApiLogRepository(db)
    filters = query.model_dump()
    # Country administrators only see their own country's calls.
    if (scope := admin_country_scope()) is not None:
        filters["country_code"] = scope
    stmt = repo.apply_filters(repo.base_stmt(), filters)
    stmt = apply_search(stmt, query.search, repo.search_cols())
    return apply_sort(stmt, ApiLog, query.sort_by, query.sort_dir, repo.default_sort)


def _with_names(db: Session, rows: list[ApiLogOut]) -> list[ApiLogOut]:
    """Fill in the app and partner names the log rows only hold ids for."""
    app_ids = {row.app_id for row in rows if row.app_id}
    participant_ids = {row.participant_id for row in rows if row.participant_id}
    apps = (
        dict(
            db.execute(
                select(ParticipantApp.app_id, ParticipantApp.name).where(ParticipantApp.app_id.in_(app_ids))
            ).all()
        )
        if app_ids
        else {}
    )
    partners = {}
    if participant_ids:
        for row in db.execute(
            select(
                Participant.participant_id,
                Participant.company_name,
                Participant.first_name,
                Participant.last_name,
                Participant.email_id,
            ).where(Participant.participant_id.in_(participant_ids))
        ).all():
            person = " ".join(part for part in (row.first_name, row.last_name) if part)
            partners[row.participant_id] = row.company_name or person or row.email_id
    return [
        row.model_copy(
            update={"app_name": apps.get(row.app_id), "participant_name": partners.get(row.participant_id)}
        )
        for row in rows
    ]


def list_api_logs(db: Session, query: ApiLogQuery) -> Page:
    page = paginate(db, _api_logs_stmt(db, query), query.page, query.limit)
    page.rows = _with_names(db, [ApiLogOut.model_validate(row) for row in page.rows])
    return page


def get_api_log(db: Session, log_id: int) -> ApiLogDetailOut | None:
    row = ApiLogRepository(db).get(log_id)
    if row is None or not assert_in_admin_scope(row.country_code):
        return None
    return _with_names(db, [ApiLogDetailOut.model_validate(row)])[0]


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
    # The page-size cap (200) must not truncate an export.
    stmt = _api_logs_stmt(db, query).limit(EXPORT_ROW_LIMIT)
    logs = [ApiLogOut.model_validate(row) for row in db.execute(stmt).scalars().all()]
    rows = [row.model_dump() for row in _with_names(db, logs)]
    return exporters.export(rows, exporters.API_LOG_COLUMNS, fmt, "API Logs")


def export_user_action_logs(
    db: Session, query: UserActionLogQuery, fmt: str
) -> tuple[bytes, str, str]:
    query.limit = EXPORT_ROW_LIMIT
    page = list_user_action_logs(db, query)
    rows = [row.model_dump() for row in page.rows]
    return exporters.export(rows, exporters.USER_ACTION_COLUMNS, fmt, "User Tracking")


def _now() -> datetime:
    return datetime.now(UTC)


def _period_start(period: DashboardPeriod, now: datetime) -> datetime:
    """Midnight UTC today, on this week's Monday, or on the 1st of this month."""
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return midnight
    if period == "week":
        return midnight - timedelta(days=midnight.weekday())
    return midnight.replace(day=1)


def dashboard(
    db: Session, country_code: str | None = None, period: DashboardPeriod = "month"
) -> DashboardResponse:
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

    now = _now()
    since = _period_start(period, now)
    hourly = period == "today"
    health = api_logs.health_since(since)
    health["success_rate"] = _rate(health["success"], health["total_calls"])

    return DashboardResponse(
        counters=counters,
        period=period,
        registrations_trend=_to_series(
            users.registrations_by_month(country_code=country_code)
        ),
        api_usage_trend=_fill_period(
            _to_series(api_logs.usage_since(since, hourly)), since, now, hourly
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


def _fill_period(
    points: list[DashboardSeriesPoint], since: datetime, now: datetime, hourly: bool
) -> list[DashboardSeriesPoint]:
    """One point per hour or day (oldest first) so quiet ones plot as zero, not a gap."""
    by_bucket = {point.label: point.value for point in points}
    filled = []
    if hourly:
        for hour in range(now.hour + 1):
            key = f"{since.date().isoformat()} {hour:02d}"
            filled.append(DashboardSeriesPoint(label=f"{hour:02d}:00", value=by_bucket.get(key, 0)))
        return filled
    for offset in range((now.date() - since.date()).days + 1):
        label = (since.date() + timedelta(days=offset)).isoformat()
        filled.append(DashboardSeriesPoint(label=label, value=by_bucket.get(label, 0)))
    return filled


def _to_series(rows) -> list[DashboardSeriesPoint]:
    return [
        DashboardSeriesPoint(label=str(label or "Unknown"), value=int(value or 0))
        for label, value in rows
    ]
