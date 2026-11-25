"""Persistence for API logs, audit trail and application events."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select

from app.core.pagination import apply_search
from app.models.app import ParticipantApp
from app.models.catalog import Product
from app.models.logs import ApiLog, SandboxLog, UserActionLog
from app.models.participant import Participant
from app.repositories.base import BaseRepository

#: ``status_class`` filter -> inclusive status range. No status (the call never
#: got an answer) counts as a server error, as on the dashboard.
STATUS_CLASSES = {"2xx": (200, 299), "3xx": (300, 399), "4xx": (400, 499), "5xx": (500, 599)}

#: Usage report groupings -> the ``api_log`` columns rows are grouped on.
USAGE_GROUPS = {
    "participant": ("participant_id",),
    "participant_endpoint": ("participant_id", "method", "endpoint_url"),
    "endpoint": ("method", "endpoint_url"),
    "app": ("participant_id", "app_id"),
    "product": ("product_id",),
    "day": ("day",),
    "status": ("status_code",),
}


class ApiLogRepository(BaseRepository[ApiLog]):
    model = ApiLog
    pk_name = "id"
    search_columns = ("endpoint_url", "transaction_id", "entity_id", "correlation_id")
    default_sort = "log_timestamp"

    def base_stmt(self, include_deleted: bool = False) -> Select:
        return select(ApiLog)

    def apply_filters(self, stmt: Select, filters: dict[str, Any]) -> Select:
        mapping = {
            "participant_id": ApiLog.participant_id,
            "source": ApiLog.source,
            "app_id": ApiLog.app_id,
            "product_id": ApiLog.product_id,
            "endpoint_id": ApiLog.endpoint_id,
            "environment": ApiLog.environment,
            "country_code": ApiLog.country_code,
            "status_code": ApiLog.status_code,
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value is not None:
                stmt = stmt.where(column == value)
        # Multi-select filters: any of the chosen partners / apps.
        if filters.get("participant_ids"):
            stmt = stmt.where(ApiLog.participant_id.in_(filters["participant_ids"]))
        if filters.get("app_ids"):
            stmt = stmt.where(ApiLog.app_id.in_(filters["app_ids"]))
        if filters.get("method"):
            stmt = stmt.where(
                func.upper(ApiLog.method) == str(filters["method"]).upper()
            )
        if filters.get("status_class") == "5xx":
            status = ApiLog.status_code
            stmt = stmt.where(or_(status.is_(None), status >= 500, status < 200))
        elif filters.get("status_class") in STATUS_CLASSES:
            low, high = STATUS_CLASSES[filters["status_class"]]
            stmt = stmt.where(ApiLog.status_code.between(low, high))
        if filters.get("date_from"):
            stmt = stmt.where(ApiLog.log_timestamp >= filters["date_from"])
        if filters.get("date_to"):
            stmt = stmt.where(
                ApiLog.log_timestamp < filters["date_to"] + timedelta(days=1)
            )
        return stmt

    # ------------------------------------------------------------ usage report
    def _outcome_columns(self) -> list:
        """Call counts per status class, mean latency and first / last call."""
        status = ApiLog.status_code
        return [
            func.count().label("total_calls"),
            func.count().filter(status.between(200, 399)).label("success_calls"),
            func.count().filter(status.between(400, 499)).label("client_errors"),
            func.count()
            .filter(or_(status.is_(None), status >= 500, status < 200))
            .label("server_errors"),
            func.avg(ApiLog.latency_ms).label("avg_latency_ms"),
            func.min(ApiLog.log_timestamp).label("first_call"),
            func.max(ApiLog.log_timestamp).label("last_call"),
        ]

    def usage_stmt(
        self, group_by: str, filters: dict[str, Any], search: str | None = None
    ) -> Select:
        """Calls grouped by ``USAGE_GROUPS[group_by]``, with names for display."""
        keys = USAGE_GROUPS[group_by]
        group_cols = [
            self._day_expr(ApiLog.log_timestamp).label("day")
            if key == "day"
            else getattr(ApiLog, key)
            for key in keys
        ]
        names = []
        if "participant_id" in keys:
            names += [
                func.max(Participant.company_name).label("company_name"),
                func.max(Participant.first_name).label("first_name"),
                func.max(Participant.last_name).label("last_name"),
                func.max(Participant.email_id).label("email_id"),
                func.max(ApiLog.country_code).label("country_code"),
            ]
        if "app_id" in keys:
            names.append(func.max(ParticipantApp.name).label("app_name"))
        if "product_id" in keys or "endpoint_url" in keys:
            names.append(
                func.max(func.coalesce(Product.display_name, Product.product_name)).label(
                    "product_name"
                )
            )
        if group_by in ("participant", "app", "product"):
            names.append(func.count(func.distinct(ApiLog.endpoint_url)).label("endpoints_used"))
        if group_by == "participant":
            names.append(func.count(func.distinct(ApiLog.app_id)).label("apps_used"))

        stmt = (
            select(*group_cols, *names, *self._outcome_columns())
            .select_from(ApiLog)
            .outerjoin(Participant, Participant.participant_id == ApiLog.participant_id)
            .outerjoin(ParticipantApp, ParticipantApp.app_id == ApiLog.app_id)
            .outerjoin(Product, Product.product_id == ApiLog.product_id)
            .group_by(*group_cols)
        )
        stmt = self.apply_filters(stmt, filters)
        if search and search.strip():
            pattern = f"%{search.strip().lower()}%"
            searchable = (
                Participant.company_name,
                Participant.first_name,
                Participant.last_name,
                Participant.email_id,
                ParticipantApp.name,
                ApiLog.endpoint_url,
            )
            stmt = stmt.where(or_(*(func.lower(col).like(pattern) for col in searchable)))
        return stmt

    def usage_totals(self, filters: dict[str, Any]) -> Any:
        stmt = select(
            *self._outcome_columns(),
            func.count(func.distinct(ApiLog.participant_id)).label("partners"),
            func.count(func.distinct(ApiLog.app_id)).label("apps"),
            func.count(func.distinct(ApiLog.endpoint_url)).label("endpoints"),
        ).select_from(ApiLog)
        return self.db.execute(self.apply_filters(stmt, filters)).one()

    def usage_breakdown(self, column_name: str, filters: dict[str, Any]) -> list:
        """``(label, value)`` calls per distinct status code, source or day."""
        column = (
            self._day_expr(ApiLog.log_timestamp)
            if column_name == "day"
            else getattr(ApiLog, column_name)
        )
        stmt = (
            select(column.label("label"), func.count().label("value"))
            .select_from(ApiLog)
            .group_by(column)
        )
        stmt = self.apply_filters(stmt, filters).order_by(column)
        return list(self.db.execute(stmt).all())

    def usage_partners(
        self,
        search: str | None,
        offset: int,
        limit: int,
        country_code: str | None = None,
    ) -> list:
        """One page of participants that made at least one call, for the partner filter.

        Uses EXISTS on the ``participant_id`` index rather than a DISTINCT over
        the whole log, so it stays cheap with many partners and many calls.
        """
        has_calls = select(ApiLog.id).where(ApiLog.participant_id == Participant.participant_id).exists()
        stmt = select(
            Participant.participant_id,
            Participant.company_name,
            Participant.first_name,
            Participant.last_name,
            Participant.email_id,
        ).where(has_calls)
        if country_code:
            stmt = stmt.where(Participant.country_code == country_code)
        stmt = apply_search(
            stmt,
            search,
            (Participant.company_name, Participant.first_name, Participant.last_name, Participant.email_id),
        )
        stmt = stmt.order_by(Participant.company_name, Participant.email_id, Participant.participant_id)
        return list(self.db.execute(stmt.offset(offset).limit(limit)).all())

    def usage_apps(
        self,
        search: str | None,
        offset: int,
        limit: int,
        participant_ids: list[int] | None = None,
        country_code: str | None = None,
    ) -> list:
        """One page of apps that made at least one call, with their partner's name."""
        has_calls = select(ApiLog.id).where(ApiLog.app_id == ParticipantApp.app_id).exists()
        stmt = (
            select(
                ParticipantApp.app_id,
                ParticipantApp.name,
                ParticipantApp.participant_id,
                Participant.company_name,
                Participant.email_id,
            )
            .join(Participant, Participant.participant_id == ParticipantApp.participant_id)
            .where(has_calls)
        )
        if participant_ids:
            stmt = stmt.where(ParticipantApp.participant_id.in_(participant_ids))
        if country_code:
            stmt = stmt.where(Participant.country_code == country_code)
        stmt = apply_search(stmt, search, (ParticipantApp.name, Participant.company_name))
        stmt = stmt.order_by(ParticipantApp.name, ParticipantApp.app_id)
        return list(self.db.execute(stmt.offset(offset).limit(limit)).all())

    def count_since(self, since: datetime, participant_id: int | None = None) -> int:
        stmt = (
            select(func.count())
            .select_from(ApiLog)
            .where(ApiLog.log_timestamp >= since)
        )
        if participant_id:
            stmt = stmt.where(ApiLog.participant_id == participant_id)
        return int(self.db.execute(stmt).scalar_one())

    def count_today(self, participant_id: int | None = None) -> int:
        start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
        return self.count_since(start, participant_id)

    def count_this_month(self, participant_id: int | None = None) -> int:
        today = date.today()
        start = datetime(today.year, today.month, 1, tzinfo=UTC)
        return self.count_since(start, participant_id)

    def _day_expr(self, column):
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            return func.to_char(column, "YYYY-MM-DD")
        return func.strftime("%Y-%m-%d", column)

    def usage_by_day(self, days: int = 30, participant_id: int | None = None):
        since = datetime.now(UTC) - timedelta(days=days)
        day = self._day_expr(ApiLog.log_timestamp)
        stmt = (
            select(day.label("label"), func.count().label("value"))
            .where(ApiLog.log_timestamp >= since)
            .group_by(day)
            .order_by(day)
        )
        if participant_id:
            stmt = stmt.where(ApiLog.participant_id == participant_id)
        return list(self.db.execute(stmt).all())

    def usage_since(self, since: datetime, hourly: bool = False):
        """Calls per hour ("YYYY-MM-DD HH") or per day ("YYYY-MM-DD") from ``since``."""
        postgres = self.db.bind is not None and self.db.bind.dialect.name == "postgresql"
        if hourly:
            bucket = (
                func.to_char(ApiLog.log_timestamp, "YYYY-MM-DD HH24")
                if postgres
                else func.strftime("%Y-%m-%d %H", ApiLog.log_timestamp)
            )
        else:
            bucket = self._day_expr(ApiLog.log_timestamp)
        stmt = (
            select(bucket.label("label"), func.count().label("value"))
            .where(ApiLog.log_timestamp >= since)
            .group_by(bucket)
            .order_by(bucket)
        )
        return list(self.db.execute(stmt).all())

    def top_endpoints(self, limit: int = 10, participant_id: int | None = None):
        stmt = (
            select(ApiLog.endpoint_url.label("label"), func.count().label("value"))
            .where(ApiLog.endpoint_url.is_not(None))
            .group_by(ApiLog.endpoint_url)
            .order_by(func.count().desc())
            .limit(limit)
        )
        if participant_id:
            stmt = stmt.where(ApiLog.participant_id == participant_id)
        return list(self.db.execute(stmt).all())

    def health_since(self, since: datetime) -> dict[str, Any]:
        """Status-class breakdown and mean latency; no status counts as a server error."""
        status = ApiLog.status_code
        stmt = select(
            func.count().label("total"),
            func.count().filter(status.between(200, 399)).label("success"),
            func.count().filter(status.between(400, 499)).label("client_errors"),
            func.count()
            .filter(or_(status.is_(None), status >= 500, status < 200))
            .label("server_errors"),
            func.avg(ApiLog.latency_ms).label("avg_latency_ms"),
        ).where(ApiLog.log_timestamp >= since)
        row = self.db.execute(stmt).one()
        return {
            "total_calls": int(row.total or 0),
            "success": int(row.success or 0),
            "client_errors": int(row.client_errors or 0),
            "server_errors": int(row.server_errors or 0),
            "avg_latency_ms": round(float(row.avg_latency_ms), 1)
            if row.avg_latency_ms is not None
            else None,
        }

    def endpoint_stats(self, since: datetime, limit: int = 10):
        """Most-called end-points with their product, success count and mean latency."""
        calls = func.count().label("calls")
        stmt = (
            select(
                ApiLog.method,
                ApiLog.endpoint_url,
                func.max(Product.display_name).label("display_name"),
                func.max(Product.product_name).label("product_name"),
                calls,
                func.count()
                .filter(ApiLog.status_code.between(200, 399))
                .label("success"),
                func.avg(ApiLog.latency_ms).label("avg_latency_ms"),
            )
            .outerjoin(Product, Product.product_id == ApiLog.product_id)
            .where(ApiLog.log_timestamp >= since, ApiLog.endpoint_url.is_not(None))
            .group_by(ApiLog.method, ApiLog.endpoint_url)
            .order_by(calls.desc(), ApiLog.endpoint_url)
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())

    def record(self, **values: Any) -> ApiLog:
        row = ApiLog(**values)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row


class UserActionLogRepository(BaseRepository[UserActionLog]):
    model = UserActionLog
    pk_name = "id"
    search_columns = ("action", "actor_name", "description", "entity")
    default_sort = "timestamp"

    def base_stmt(self, include_deleted: bool = False) -> Select:
        return select(UserActionLog)

    def apply_filters(self, stmt: Select, filters: dict[str, Any]) -> Select:
        mapping = {
            "actor_type": UserActionLog.actor_type,
            "actor_id": UserActionLog.actor_id,
            "action": UserActionLog.action,
            "entity": UserActionLog.entity,
            "country_code": UserActionLog.country_code,
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value is not None:
                stmt = stmt.where(column == value)
        if filters.get("date_from"):
            stmt = stmt.where(UserActionLog.timestamp >= filters["date_from"])
        if filters.get("date_to"):
            stmt = stmt.where(
                UserActionLog.timestamp < filters["date_to"] + timedelta(days=1)
            )
        return stmt

    def record(self, **values: Any) -> UserActionLog:
        row = UserActionLog(**values)
        self.db.add(row)
        self.db.commit()
        return row


class SandboxLogRepository(BaseRepository[SandboxLog]):
    model = SandboxLog
    pk_name = "id"
    search_columns = ("message", "level")
    default_sort = "timestamp"

    def base_stmt(self, include_deleted: bool = False) -> Select:
        return select(SandboxLog)
