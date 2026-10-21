"""Persistence for API logs, audit trail and application events."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select

from app.models.catalog import Product
from app.models.logs import ApiLog, SandboxLog, UserActionLog
from app.repositories.base import BaseRepository


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
        if filters.get("method"):
            stmt = stmt.where(
                func.upper(ApiLog.method) == str(filters["method"]).upper()
            )
        if filters.get("date_from"):
            stmt = stmt.where(ApiLog.log_timestamp >= filters["date_from"])
        if filters.get("date_to"):
            stmt = stmt.where(
                ApiLog.log_timestamp < filters["date_to"] + timedelta(days=1)
            )
        return stmt

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
