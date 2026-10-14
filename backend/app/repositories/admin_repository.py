"""Persistence for admin users, roles, permissions and sessions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import PERMISSION_TREE
from app.models.admin import (
    AdmPermission,
    AdmRole,
    AdmRolePermission,
    AdmToken,
    AdmUser,
)
from app.repositories.base import BaseRepository


class AdminUserRepository(BaseRepository[AdmUser]):
    model = AdmUser
    pk_name = "admin_id"
    search_columns = ("first_name", "last_name", "email_id", "login_name", "mobile_no")

    def get_by_login(self, identifier: str) -> AdmUser | None:
        """Sign-in accepts either the login name or the email address."""
        ident = (identifier or "").strip().lower()
        stmt = self.base_stmt().where(func.lower(AdmUser.email_id) == ident)
        user = self.db.execute(stmt).scalars().first()
        if user:
            return user
        stmt = self.base_stmt().where(func.lower(AdmUser.login_name) == ident)
        return self.db.execute(stmt).scalars().first()

    def login_name_taken(
        self, login_name: str, exclude_admin_id: int | None = None
    ) -> bool:
        stmt = self.base_stmt().where(
            func.lower(AdmUser.login_name) == login_name.strip().lower()
        )
        if exclude_admin_id:
            stmt = stmt.where(AdmUser.admin_id != exclude_admin_id)
        return self.db.execute(stmt).scalars().first() is not None

    def email_taken(self, email: str, exclude_admin_id: int | None = None) -> bool:
        stmt = self.base_stmt().where(
            func.lower(AdmUser.email_id) == email.strip().lower()
        )
        if exclude_admin_id:
            stmt = stmt.where(AdmUser.admin_id != exclude_admin_id)
        return self.db.execute(stmt).scalars().first() is not None

    def get_by_set_pass_token(self, token: str) -> AdmUser | None:
        return self.get_by(set_pass_token=token)

    def list_with_roles(self, **kwargs: Any):
        """Paginated list joined to the role, so grids can show the role name."""
        stmt = (
            select(AdmUser, AdmRole.role_name)
            .join(AdmRole, AdmUser.role_id == AdmRole.role_id, isouter=True)
            .where(AdmUser.is_deleted.is_(False))
        )
        return stmt


class RoleRepository(BaseRepository[AdmRole]):
    model = AdmRole
    pk_name = "role_id"
    search_columns = ("role_name",)

    def name_taken(self, role_name: str, exclude_role_id: int | None = None) -> bool:
        stmt = self.base_stmt().where(
            func.lower(AdmRole.role_name) == role_name.strip().lower()
        )
        if exclude_role_id:
            stmt = stmt.where(AdmRole.role_id != exclude_role_id)
        return self.db.execute(stmt).scalars().first() is not None

    def user_count(self, role_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(AdmUser)
            .where(AdmUser.role_id == role_id, AdmUser.is_deleted.is_(False))
        )
        return int(self.db.execute(stmt).scalar_one())

    def user_counts(self, role_ids: list[int]) -> dict[int, int]:
        if not role_ids:
            return {}
        stmt = (
            select(AdmUser.role_id, func.count())
            .where(AdmUser.role_id.in_(role_ids), AdmUser.is_deleted.is_(False))
            .group_by(AdmUser.role_id)
        )
        return {
            int(role_id): int(total) for role_id, total in self.db.execute(stmt).all()
        }

    def dropdown(self) -> list[AdmRole]:
        stmt = (
            self.base_stmt()
            .where(AdmRole.is_enabled.is_(True))
            .order_by(AdmRole.role_name)
        )
        return list(self.db.execute(stmt).scalars().all())


class PermissionRepository:
    """Permission catalogue plus the role grants layered on top of it."""

    def __init__(self, db: Session):
        self.db = db

    def all_permissions(self) -> list[AdmPermission]:
        stmt = select(AdmPermission).order_by(
            AdmPermission.sort_order, AdmPermission.permission_id
        )
        return list(self.db.execute(stmt).scalars().all())

    def allowed_ids_for_role(self, role_id: int | None) -> set[int]:
        if not role_id:
            return set()
        stmt = select(AdmRolePermission.permission_id).where(
            AdmRolePermission.role_id == role_id,
            AdmRolePermission.is_allowed.is_(True),
        )
        return {int(row) for row in self.db.execute(stmt).scalars().all()}

    def allowed_ids_for_roles(self, role_ids: list[int]) -> dict[int, set[int]]:
        """Grants for several roles at once, keyed by role id."""
        if not role_ids:
            return {}
        stmt = select(AdmRolePermission.role_id, AdmRolePermission.permission_id).where(
            AdmRolePermission.role_id.in_(role_ids),
            AdmRolePermission.is_allowed.is_(True),
        )
        grants: dict[int, set[int]] = {int(role_id): set() for role_id in role_ids}
        for role_id, permission_id in self.db.execute(stmt).all():
            grants[int(role_id)].add(int(permission_id))
        return grants

    def permission_flags(
        self, role_id: int | None, is_master: bool
    ) -> list[dict[str, Any]]:
        """``[{"id": 1, "status": True}, ...]`` - the shape the console expects.

        A master account is granted everything without consulting the grants
        table, matching the reference behaviour.
        """
        if is_master:
            return [{"id": int(pid), "status": True} for pid in PERMISSION_TREE]
        allowed = self.allowed_ids_for_role(role_id)
        return [
            {"id": int(pid), "status": int(pid) in allowed} for pid in PERMISSION_TREE
        ]

    def replace_role_permissions(
        self, role_id: int, permission_ids: list[int], actor_id: int | None = None
    ) -> None:
        """Rewrite a role's grants in one transaction."""
        existing = {
            row.permission_id: row
            for row in self.db.execute(
                select(AdmRolePermission).where(AdmRolePermission.role_id == role_id)
            )
            .scalars()
            .all()
        }
        wanted = {int(pid) for pid in permission_ids}

        for pid in wanted:
            row = existing.get(pid)
            if row:
                row.is_allowed = True
                row.modify_by = actor_id
            else:
                self.db.add(
                    AdmRolePermission(
                        role_id=role_id,
                        permission_id=pid,
                        is_allowed=True,
                        added_by=actor_id,
                        modify_by=actor_id,
                    )
                )
        for pid, row in existing.items():
            if pid not in wanted:
                row.is_allowed = False
                row.modify_by = actor_id
        self.db.commit()

    def sync_catalogue(self) -> int:
        """Upsert ``PERMISSION_TREE`` into ``adm_permission``.

        Runs at startup so a newly added console screen becomes grantable
        without a manual migration.
        """
        existing = {p.permission_id: p for p in self.all_permissions()}
        changed = 0
        for order, (pid, (label, parent, has_sub)) in enumerate(
            PERMISSION_TREE.items()
        ):
            row = existing.get(int(pid))
            if row is None:
                self.db.add(
                    AdmPermission(
                        permission_id=int(pid),
                        menu_name=label,
                        parent_id=int(parent) if parent else None,
                        has_submenu=has_sub,
                        sort_order=order,
                    )
                )
                changed += 1
            elif (row.menu_name, row.parent_id, row.has_submenu) != (
                label,
                int(parent) if parent else None,
                has_sub,
            ):
                row.menu_name = label
                row.parent_id = int(parent) if parent else None
                row.has_submenu = has_sub
                row.sort_order = order
                changed += 1
        if changed:
            self.db.commit()
        return changed


class AdminTokenRepository(BaseRepository[AdmToken]):
    model = AdmToken
    pk_name = "token_id"
    default_sort = "added_date"

    def get_active(self, auth_key: str) -> AdmToken | None:
        stmt = select(AdmToken).where(
            AdmToken.unique_id == auth_key, AdmToken.is_logout.is_(False)
        )
        return self.db.execute(stmt).scalars().first()

    def touch(self, token: AdmToken) -> None:
        token.last_action = datetime.now(UTC)
        self.db.commit()

    def logout(self, token: AdmToken) -> None:
        token.is_logout = True
        token.logout_time = datetime.now(UTC)
        self.db.commit()

    def logout_all(self, admin_id: int) -> int:
        stmt = select(AdmToken).where(
            AdmToken.admin_id == admin_id, AdmToken.is_logout.is_(False)
        )
        rows = list(self.db.execute(stmt).scalars().all())
        now = datetime.now(UTC)
        for row in rows:
            row.is_logout = True
            row.logout_time = now
        if rows:
            self.db.commit()
        return len(rows)
