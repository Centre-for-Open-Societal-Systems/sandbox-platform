"""Persistence for API products, apps, their product grants and credentials."""

from __future__ import annotations

from sqlalchemy import Select, func, or_, select

from app.models.app import (
    ApiProduct,
    ApiProductEndpoint,
    ParticipantApp,
    ParticipantAppCredential,
    ParticipantAppProduct,
)
from app.models.catalog import Endpoint
from app.models.enums import AppStatus, CredentialStatus, SubscriptionStatus
from app.models.participant import Participant
from app.repositories.base import BaseRepository


class ApiProductRepository(BaseRepository[ApiProduct]):
    model = ApiProduct
    pk_name = "api_product_id"
    search_columns = ("name", "display_name", "description")

    def name_taken(self, name: str, exclude_id: int | None = None) -> bool:
        stmt = self.base_stmt().where(func.lower(ApiProduct.name) == name.lower())
        if exclude_id:
            stmt = stmt.where(ApiProduct.api_product_id != exclude_id)
        return self.db.execute(stmt).first() is not None

    def published(self, country_code: str | None = None) -> list[ApiProduct]:
        stmt = self.base_stmt().where(
            ApiProduct.is_published.is_(True), ApiProduct.is_enabled.is_(True)
        )
        if country_code:
            stmt = stmt.where(
                (ApiProduct.country_code == country_code) | ApiProduct.country_code.is_(None)
            )
        stmt = stmt.order_by(ApiProduct.sort_order, ApiProduct.display_name)
        return list(self.db.execute(stmt).scalars())

    def endpoint_ids(self, api_product_ids: list[int]) -> dict[int, list[int]]:
        if not api_product_ids:
            return {}
        stmt = (
            select(ApiProductEndpoint.api_product_id, ApiProductEndpoint.endpoint_id)
            .join(Endpoint, Endpoint.endpoint_id == ApiProductEndpoint.endpoint_id)
            .where(
                ApiProductEndpoint.api_product_id.in_(api_product_ids),
                Endpoint.is_deleted.is_(False),
            )
            .order_by(ApiProductEndpoint.endpoint_id)
        )
        result: dict[int, list[int]] = {pid: [] for pid in api_product_ids}
        for product_id, endpoint_id in self.db.execute(stmt):
            result[product_id].append(endpoint_id)
        return result

    def endpoints(self, api_product_id: int) -> list[Endpoint]:
        stmt = (
            select(Endpoint)
            .join(ApiProductEndpoint, ApiProductEndpoint.endpoint_id == Endpoint.endpoint_id)
            .where(
                ApiProductEndpoint.api_product_id == api_product_id,
                Endpoint.is_deleted.is_(False),
            )
            .order_by(Endpoint.product_id, Endpoint.sort_order, Endpoint.endpoint_id)
        )
        return list(self.db.execute(stmt).scalars())

    def replace_endpoints(self, product: ApiProduct, endpoint_ids: list[int]) -> None:
        wanted = set(endpoint_ids)
        for link in list(product.endpoints):
            if link.endpoint_id not in wanted:
                product.endpoints.remove(link)
        have = {link.endpoint_id for link in product.endpoints}
        for endpoint_id in endpoint_ids:
            if endpoint_id not in have:
                product.endpoints.append(ApiProductEndpoint(endpoint_id=endpoint_id))
                have.add(endpoint_id)

    def subscriber_app_ids(self, api_product_id: int) -> list[int]:
        """Apps (not deleted) with approved access; the same apps ``subscription_counts`` counts."""
        stmt = (
            select(ParticipantAppProduct.app_id)
            .join(ParticipantApp, ParticipantApp.app_id == ParticipantAppProduct.app_id)
            .where(
                ParticipantAppProduct.api_product_id == api_product_id,
                ParticipantAppProduct.status == int(SubscriptionStatus.APPROVED),
                ParticipantApp.is_deleted.is_(False),
            )
        )
        return list(self.db.execute(stmt).scalars())

    def subscription_counts(self, api_product_ids: list[int]) -> dict[int, int]:
        if not api_product_ids:
            return {}
        stmt = (
            select(ParticipantAppProduct.api_product_id, func.count())
            .join(ParticipantApp, ParticipantApp.app_id == ParticipantAppProduct.app_id)
            .where(
                ParticipantAppProduct.api_product_id.in_(api_product_ids),
                ParticipantAppProduct.status == int(SubscriptionStatus.APPROVED),
                ParticipantApp.is_deleted.is_(False),
            )
            .group_by(ParticipantAppProduct.api_product_id)
        )
        return dict(self.db.execute(stmt).all())


class ParticipantAppRepository(BaseRepository[ParticipantApp]):
    model = ParticipantApp
    pk_name = "app_id"
    search_columns = ("name", "description", "gateway_consumer")

    def for_participant(self, participant_id: int) -> list[ParticipantApp]:
        stmt = (
            self.base_stmt()
            .where(ParticipantApp.participant_id == participant_id)
            .order_by(ParticipantApp.added_date.desc())
        )
        return list(self.db.execute(stmt).scalars())

    def get_owned(self, participant_id: int, unique_id: str) -> ParticipantApp | None:
        return self.get_by(participant_id=participant_id, unique_id=unique_id)

    def name_taken(
        self, participant_id: int, name: str, environment: str, exclude_id: int | None = None
    ) -> bool:
        stmt = self.base_stmt().where(
            ParticipantApp.participant_id == participant_id,
            ParticipantApp.environment == environment,
            func.lower(ParticipantApp.name) == name.lower(),
        )
        if exclude_id:
            stmt = stmt.where(ParticipantApp.app_id != exclude_id)
        return self.db.execute(stmt).first() is not None

    def admin_stmt(
        self,
        status: int | None = None,
        participant_id: int | None = None,
        api_product_id: int | None = None,
        pending_only: bool = False,
        country_code: str | None = None,
    ) -> Select:
        stmt = self.base_stmt().join(
            Participant, Participant.participant_id == ParticipantApp.participant_id
        )
        if status is not None:
            stmt = stmt.where(ParticipantApp.status == status)
        if participant_id is not None:
            stmt = stmt.where(ParticipantApp.participant_id == participant_id)
        if country_code:
            stmt = stmt.where(Participant.country_code == country_code)
        if api_product_id is not None:
            sub = select(ParticipantAppProduct.app_id).where(
                ParticipantAppProduct.api_product_id == api_product_id
            )
            stmt = stmt.where(ParticipantApp.app_id.in_(sub))
        if pending_only:
            stmt = stmt.where(self._awaiting_decision())
        return stmt

    @staticmethod
    def _awaiting_decision():
        """A new app, or an active app with a product request still open."""
        waiting = select(ParticipantAppProduct.app_id).where(
            ParticipantAppProduct.status == int(SubscriptionStatus.PENDING)
        )
        return or_(
            ParticipantApp.status == int(AppStatus.PENDING),
            ParticipantApp.app_id.in_(waiting),
        )

    def pending_count(self) -> int:
        stmt = self.base_stmt().with_only_columns(func.count()).where(self._awaiting_decision())
        return int(self.db.execute(stmt).scalar_one())


class AppSubscriptionRepository(BaseRepository[ParticipantAppProduct]):
    model = ParticipantAppProduct
    pk_name = "id"

    def for_app(self, app_id: int) -> list[ParticipantAppProduct]:
        stmt = (
            select(ParticipantAppProduct)
            .where(ParticipantAppProduct.app_id == app_id)
            .order_by(ParticipantAppProduct.id)
        )
        return list(self.db.execute(stmt).scalars())

    def find(self, app_id: int, api_product_id: int) -> ParticipantAppProduct | None:
        return self.get_by(app_id=app_id, api_product_id=api_product_id)


class AppCredentialRepository(BaseRepository[ParticipantAppCredential]):
    model = ParticipantAppCredential
    pk_name = "credential_id"
    default_sort = "issued_date"

    def for_app(self, app_id: int, active_only: bool = False) -> list[ParticipantAppCredential]:
        stmt = select(ParticipantAppCredential).where(ParticipantAppCredential.app_id == app_id)
        if active_only:
            stmt = stmt.where(ParticipantAppCredential.status == int(CredentialStatus.ACTIVE))
        stmt = stmt.order_by(ParticipantAppCredential.issued_date.desc())
        return list(self.db.execute(stmt).scalars())

    def active_count(self, app_id: int) -> int:
        return self.count(app_id=app_id, status=int(CredentialStatus.ACTIVE))
