"""Persistence for participants, sessions, promotion requests and queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, func, or_, select

from app.models.enums import ApprovalStatus, Environment
from app.models.participant import (
    Participant,
    ParticipantQuery,
    ParticipantRequestInfo,
    ParticipantToken,
)
from app.repositories.base import BaseRepository


class ParticipantRepository(BaseRepository[Participant]):
    model = Participant
    pk_name = "participant_id"
    search_columns = (
        "company_name",
        "first_name",
        "last_name",
        "email_id",
        "mobile_number",
        "organization_registration_number",
    )
    default_sort = "register_date"

    def get_by_email(self, email_id: str) -> Participant | None:
        """Sign-in and duplicate checks both key off the email address."""
        ident = (email_id or "").strip().lower()
        stmt = self.base_stmt().where(func.lower(Participant.email_id) == ident)
        return self.db.execute(stmt).scalars().first()

    def email_taken(self, email_id: str) -> bool:
        ident = (email_id or "").strip().lower()
        row = self.db.execute(
            select(Participant.participant_id).where(
                func.lower(Participant.email_id) == ident,
                Participant.is_deleted.is_(False),
            )
        ).first()
        return row is not None

    def get_by_reset_token(self, token: str) -> Participant | None:
        return self.get_by(reset_pass_token=token)

    def environment_stmt(self, environment: Environment | None) -> Select:
        """List filtered by promotion state - the console environment tabs."""
        stmt = self.base_stmt()
        if environment == Environment.UAT:
            stmt = stmt.where(Participant.is_uat_approved.is_(True))
        elif environment == Environment.PRODUCTION:
            stmt = stmt.where(Participant.is_prod_approved.is_(True))
        elif environment == Environment.SANDBOX:
            stmt = stmt.where(Participant.is_sandbox_approved.is_(True))
        return stmt

    def pending_stmt(self, environment: Environment) -> Select:
        """Awaiting an admin decision for the given environment.

        Only users who have actually *asked* for the environment appear, which
        is why the request flags exist for UAT as well as production - listing
        everyone not yet approved would show the whole table.
        """
        stmt = self.base_stmt()
        if environment == Environment.PRODUCTION:
            return stmt.where(
                Participant.is_prod_requested.is_(True),
                Participant.is_prod_approved.is_(False),
                Participant.is_prod_rejected.is_(False),
            )
        if environment == Environment.UAT:
            return stmt.where(
                Participant.is_uat_requested.is_(True),
                Participant.is_uat_approved.is_(False),
                Participant.is_uat_rejected.is_(False),
            )
        return stmt.where(
            Participant.is_email_verified.is_(True),
            Participant.is_approved == int(ApprovalStatus.PENDING),
            Participant.is_rejected.is_(False),
        )

    def rejected_stmt(self, environment: Environment | None = None) -> Select:
        stmt = self.base_stmt()
        if environment == Environment.UAT:
            return stmt.where(Participant.is_uat_rejected.is_(True))
        if environment == Environment.PRODUCTION:
            return stmt.where(Participant.is_prod_rejected.is_(True))
        return stmt.where(
            or_(
                Participant.is_rejected.is_(True),
                Participant.is_uat_rejected.is_(True),
                Participant.is_prod_rejected.is_(True),
            )
        )

    def apply_common_filters(self, stmt: Select, filters: dict[str, Any]) -> Select:
        mapping = {
            "country_code": Participant.country_code,
            "admin_area_code_l1": Participant.admin_area_code_l1,
            "participant_type_id": Participant.participant_type_id,
            "profile_type": Participant.profile_type,
            "is_approved": Participant.is_approved,
            "is_rejected": Participant.is_rejected,
        }
        for key, column in mapping.items():
            value = filters.get(key)
            if value is not None:
                stmt = stmt.where(column == value)
        if filters.get("date_from"):
            stmt = stmt.where(Participant.register_date >= filters["date_from"])
        if filters.get("date_to"):
            # Inclusive of the whole end day.
            stmt = stmt.where(
                Participant.register_date < filters["date_to"] + timedelta(days=1)
            )
        return stmt

    def counts_by_status(self, country_code: str | None = None) -> dict[str, int]:
        def _count(*conditions) -> int:
            stmt = (
                select(func.count())
                .select_from(Participant)
                .where(Participant.is_deleted.is_(False), *conditions)
            )
            if country_code:
                stmt = stmt.where(Participant.country_code == country_code)
            return int(self.db.execute(stmt).scalar_one())

        return {
            "total_participants": _count(),
            "unverified_participants": _count(Participant.is_email_verified.is_(False)),
            "sandbox_participants": _count(Participant.is_sandbox_approved.is_(True)),
            "uat_pending": _count(
                Participant.is_uat_requested.is_(True),
                Participant.is_uat_approved.is_(False),
                Participant.is_uat_rejected.is_(False),
            ),
            "uat_participants": _count(Participant.is_uat_approved.is_(True)),
            "prod_pending": _count(
                Participant.is_prod_requested.is_(True),
                Participant.is_prod_approved.is_(False),
                Participant.is_prod_rejected.is_(False),
            ),
            "prod_participants": _count(Participant.is_prod_approved.is_(True)),
            "rejected_participants": _count(
                or_(
                    Participant.is_rejected.is_(True),
                    Participant.is_uat_rejected.is_(True),
                    Participant.is_prod_rejected.is_(True),
                )
            ),
        }

    def purge_unverified(self, older_than_days: int = 30) -> int:
        """Drop abandoned signups that never verified their email address."""
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        rows = list(
            self.db.execute(
                self.base_stmt().where(
                    Participant.register_date < cutoff,
                    Participant.is_email_verified.is_(False),
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            row.is_deleted = True
        if rows:
            self.db.commit()
        return len(rows)

    def _month_expr(self, column):
        """``YYYY-MM`` bucket, spelled for whichever dialect is connected."""
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            return func.to_char(column, "YYYY-MM")
        return func.strftime("%Y-%m", column)

    def registrations_by_month(self, months: int = 12, country_code: str | None = None):
        since = datetime.now(UTC) - timedelta(days=31 * months)
        month = self._month_expr(Participant.register_date)
        stmt = (
            select(month.label("label"), func.count().label("value"))
            .where(
                Participant.is_deleted.is_(False), Participant.register_date >= since
            )
            .group_by(month)
            .order_by(month)
        )
        if country_code:
            stmt = stmt.where(Participant.country_code == country_code)
        return list(self.db.execute(stmt).all())


class ParticipantTokenRepository(BaseRepository[ParticipantToken]):
    model = ParticipantToken
    pk_name = "token_id"
    default_sort = "added_date"

    def get_active(self, auth_key: str) -> ParticipantToken | None:
        stmt = select(ParticipantToken).where(
            ParticipantToken.unique_id == auth_key,
            ParticipantToken.is_logout.is_(False),
        )
        return self.db.execute(stmt).scalars().first()

    def touch(self, token: ParticipantToken) -> None:
        token.last_action = datetime.now(UTC)
        self.db.commit()

    def logout(self, token: ParticipantToken) -> None:
        token.is_logout = True
        token.logout_time = datetime.now(UTC)
        self.db.commit()


class ParticipantRequestRepository(BaseRepository[ParticipantRequestInfo]):
    model = ParticipantRequestInfo
    pk_name = "request_id"
    default_sort = "added_date"

    def latest_for(
        self, participant_id: int, environment: Environment
    ) -> ParticipantRequestInfo | None:
        stmt = (
            select(ParticipantRequestInfo)
            .where(
                ParticipantRequestInfo.participant_id == participant_id,
                ParticipantRequestInfo.target_environment == str(environment),
            )
            .order_by(ParticipantRequestInfo.added_date.desc())
        )
        return self.db.execute(stmt).scalars().first()

    def has_open_request(self, participant_id: int, environment: Environment) -> bool:
        latest = self.latest_for(participant_id, environment)
        return bool(latest and latest.status == int(ApprovalStatus.PENDING))


class ParticipantQueryRepository(BaseRepository[ParticipantQuery]):
    model = ParticipantQuery
    pk_name = "query_id"
    search_columns = ("subject", "description")
    default_sort = "added_date"

    def open_count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(ParticipantQuery)
            .where(ParticipantQuery.status.in_([0, 1]))
        )
        return int(self.db.execute(stmt).scalar_one())

    def search_stmt(self, search: str | None) -> Select:
        """Queries whose text, or whose participant, matches ``search``."""
        stmt = self.base_stmt()
        if not search or not search.strip():
            return stmt
        pattern = f"%{search.strip().lower()}%"
        matching_participants = select(Participant.participant_id).where(
            or_(
                func.lower(Participant.first_name).like(pattern),
                func.lower(Participant.last_name).like(pattern),
                func.lower(Participant.email_id).like(pattern),
                func.lower(Participant.company_name).like(pattern),
            )
        )
        return stmt.where(
            or_(
                func.lower(ParticipantQuery.subject).like(pattern),
                func.lower(ParticipantQuery.description).like(pattern),
                ParticipantQuery.participant_id.in_(matching_participants),
            )
        )
