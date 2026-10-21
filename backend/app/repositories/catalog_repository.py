"""Persistence for the API catalogue."""

from __future__ import annotations

from sqlalchemy import Select, func, select

from app.models.catalog import Endpoint, EndpointSchema, MapperData, Product
from app.models.masters import ProductCategory
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    model = Product
    pk_name = "product_id"
    search_columns = ("product_name", "display_name", "description")
    default_sort = "sort_order"

    def name_taken(self, product_name: str, exclude_id: int | None = None) -> bool:
        stmt = self.base_stmt().where(
            func.lower(Product.product_name) == product_name.strip().lower()
        )
        if exclude_id:
            stmt = stmt.where(Product.product_id != exclude_id)
        return self.db.execute(stmt).scalars().first() is not None

    def published_stmt(self, country_code: str | None = None) -> Select:
        """Catalogue visible to the public portal.

        A product with no ``country_code`` is network-wide, so a member
        country sees its own products plus the shared ones.
        """
        stmt = self.base_stmt().where(Product.is_published.is_(True))
        if country_code:
            stmt = stmt.where(
                (Product.country_code == country_code)
                | (Product.country_code.is_(None))
            )
        return stmt.order_by(Product.sort_order, Product.product_name)

    def catalog_version(self) -> str:
        """Cheap fingerprint of the catalogue: changes whenever a product or
        end-point is created, edited, published, unpublished or deleted."""
        stmt = select(
            select(func.max(Product.modify_date)).scalar_subquery(),
            select(func.count(Product.product_id)).scalar_subquery(),
            select(func.max(Endpoint.modify_date)).scalar_subquery(),
            select(func.count(Endpoint.endpoint_id)).scalar_subquery(),
        )
        return "|".join(str(value) for value in self.db.execute(stmt).one())

    def published_endpoint_rows(self, product_ids: list[int]) -> list:
        """Menu columns of the published end-points of many products, one query."""
        if not product_ids:
            return []
        stmt = (
            select(
                Endpoint.product_id,
                Endpoint.endpoint_id,
                Endpoint.display_name,
                Endpoint.endpoint_url,
                Endpoint.method,
                Endpoint.api_type,
            )
            .where(
                Endpoint.product_id.in_(product_ids),
                Endpoint.is_deleted.is_(False),
                Endpoint.is_published.is_(True),
            )
            .order_by(Endpoint.product_id, Endpoint.sort_order, Endpoint.endpoint_id)
        )
        return list(self.db.execute(stmt).all())

    def endpoint_counts(self, product_ids: list[int]) -> dict[int, int]:
        if not product_ids:
            return {}
        stmt = (
            select(Endpoint.product_id, func.count())
            .where(Endpoint.product_id.in_(product_ids), Endpoint.is_deleted.is_(False))
            .group_by(Endpoint.product_id)
        )
        return {int(pid): int(count) for pid, count in self.db.execute(stmt).all()}

    def category_names(self, category_ids: list[int]) -> dict[int, str]:
        ids = [c for c in category_ids if c]
        if not ids:
            return {}
        stmt = select(ProductCategory.category_id, ProductCategory.category_name).where(
            ProductCategory.category_id.in_(ids)
        )
        return {int(cid): name for cid, name in self.db.execute(stmt).all()}

    def counts(self) -> tuple[int, int]:
        total = self.count()
        published = self.count(is_published=True)
        return total, published


class EndpointRepository(BaseRepository[Endpoint]):
    model = Endpoint
    pk_name = "endpoint_id"
    search_columns = ("display_name", "endpoint_url", "description")
    default_sort = "sort_order"

    def for_product(
        self, product_id: int, published_only: bool = False
    ) -> list[Endpoint]:
        stmt = self.base_stmt().where(Endpoint.product_id == product_id)
        if published_only:
            stmt = stmt.where(Endpoint.is_published.is_(True))
        return list(
            self.db.execute(stmt.order_by(Endpoint.sort_order, Endpoint.endpoint_id))
            .scalars()
            .all()
        )

    def find_by_route(self, product_id: int, method: str, path: str) -> Endpoint | None:
        stmt = self.base_stmt().where(
            Endpoint.product_id == product_id,
            func.upper(Endpoint.method) == (method or "").upper(),
            Endpoint.endpoint_url == path,
        )
        return self.db.execute(stmt).scalars().first()

    def product_names(self, product_ids: list[int]) -> dict[int, str]:
        ids = [p for p in product_ids if p]
        if not ids:
            return {}
        stmt = select(Product.product_id, Product.product_name).where(
            Product.product_id.in_(ids)
        )
        return {int(pid): name for pid, name in self.db.execute(stmt).all()}

    def top_called(self, limit: int = 10) -> list[Endpoint]:
        """Most-used endpoints, joined from the API log."""
        from app.models.logs import ApiLog

        stmt = (
            select(Endpoint, func.count(ApiLog.id).label("hits"))
            .join(ApiLog, ApiLog.endpoint_id == Endpoint.endpoint_id)
            .where(Endpoint.is_deleted.is_(False))
            .group_by(Endpoint.endpoint_id)
            .order_by(func.count(ApiLog.id).desc())
            .limit(limit)
        )
        return list(self.db.execute(stmt).all())


class EndpointSchemaRepository(BaseRepository[EndpointSchema]):
    model = EndpointSchema
    pk_name = "schema_id"
    default_sort = "status_code"

    def for_endpoint(self, endpoint_id: int) -> list[EndpointSchema]:
        stmt = (
            self.base_stmt()
            .where(EndpointSchema.endpoint_id == endpoint_id)
            .order_by(EndpointSchema.status_code)
        )
        return list(self.db.execute(stmt).scalars().all())

    def get_for_status(
        self, endpoint_id: int, status_code: str = "200"
    ) -> EndpointSchema | None:
        return self.get_by(endpoint_id=endpoint_id, status_code=status_code)

    def status_taken(
        self, endpoint_id: int, status_code: str, exclude_id: int | None = None
    ) -> bool:
        stmt = self.base_stmt().where(
            EndpointSchema.endpoint_id == endpoint_id,
            EndpointSchema.status_code == status_code,
        )
        if exclude_id:
            stmt = stmt.where(EndpointSchema.schema_id != exclude_id)
        return self.db.execute(stmt).scalars().first() is not None


class MapperRepository(BaseRepository[MapperData]):
    model = MapperData
    pk_name = "mapper_id"
    search_columns = ("usecase_name", "description")
    default_sort = "usecase_name"

    def name_taken(self, usecase_name: str, exclude_id: int | None = None) -> bool:
        stmt = self.base_stmt().where(
            func.lower(MapperData.usecase_name) == usecase_name.strip().lower()
        )
        if exclude_id:
            stmt = stmt.where(MapperData.mapper_id != exclude_id)
        return self.db.execute(stmt).scalars().first() is not None

    def in_use(self, mapper_id: int) -> bool:
        stmt = (
            select(func.count())
            .select_from(Endpoint)
            .where(Endpoint.mapper_id == mapper_id, Endpoint.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one()) > 0
