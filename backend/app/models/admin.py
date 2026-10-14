"""Back-office identity: admin users, roles, permissions and sessions.

Ports ``adm_user`` / ``adm_role`` / ``adm_permission`` / ``adm_role_permission``
/ ``adm_token`` from the reference schema. ``state_lgd_code`` becomes
``admin_area_code`` plus ``country_code`` so an admin can be scoped to one
country, one region inside it, or the whole network.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import AuditMixin, BigIntPk, SoftDeleteMixin, UniqueIdMixin, utcnow


class AdmRole(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "adm_role"

    role_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_level: Mapped[int | None] = mapped_column(Integer)
    is_editable: Mapped[bool] = mapped_column(Boolean, default=True)
    #: 0 = not applicable, 1 = maker, 2 = checker
    checker_maker: Mapped[int] = mapped_column(Integer, default=0)

    users: Mapped[list[AdmUser]] = relationship(back_populates="role")
    permissions: Mapped[list[AdmRolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class AdmPermission(Base):
    __tablename__ = "adm_permission"

    permission_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    menu_name: Mapped[str | None] = mapped_column(String(500))
    has_submenu: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[int | None] = mapped_column(BigInteger)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class AdmRolePermission(Base, AuditMixin):
    __tablename__ = "adm_role_permission"

    id: Mapped[int] = mapped_column(BigIntPk, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("adm_role.role_id"), nullable=False, index=True
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("adm_permission.permission_id"), nullable=False, index=True
    )
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=False)

    role: Mapped[AdmRole] = relationship(back_populates="permissions")


class AdmUser(Base, UniqueIdMixin, AuditMixin, SoftDeleteMixin):
    __tablename__ = "adm_user"

    admin_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    first_name: Mapped[str | None] = mapped_column(String(50))
    last_name: Mapped[str | None] = mapped_column(String(50))
    email_id: Mapped[str | None] = mapped_column(String(150), index=True)
    mobile_no: Mapped[str | None] = mapped_column(String(50))
    login_name: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    login_pass: Mapped[str | None] = mapped_column(String(4000))
    description: Mapped[str | None] = mapped_column(String(500))

    is_master: Mapped[bool] = mapped_column(Boolean, default=False)
    is_activated: Mapped[bool] = mapped_column(Boolean, default=False)
    activate_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    role_id: Mapped[int | None] = mapped_column(
        ForeignKey("adm_role.role_id"), index=True
    )
    account_id: Mapped[int | None] = mapped_column(BigInteger)

    # Geographic scope. Empty country_code == network-wide (OAN operator).
    country_code: Mapped[str | None] = mapped_column(String(2), index=True)
    admin_area_code: Mapped[str | None] = mapped_column(String(20), index=True)

    # Single-use tokens for the invite / reset-password flows.
    set_pass_token: Mapped[str | None] = mapped_column(String(255), index=True)
    set_pass_token_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    role: Mapped[AdmRole | None] = relationship(back_populates="users")

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p).strip()


class AdmToken(Base, UniqueIdMixin):
    """One row per admin sign-in; ``unique_id`` is the ``x-auth-key``."""

    __tablename__ = "adm_token"

    token_id: Mapped[int] = mapped_column(
        BigIntPk, primary_key=True, autoincrement=True
    )
    admin_id: Mapped[int | None] = mapped_column(
        ForeignKey("adm_user.admin_id"), index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(2500))
    device_name: Mapped[str | None] = mapped_column(String(100))
    ip_location: Mapped[str | None] = mapped_column(String(100))
    added_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    last_action: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    is_logout: Mapped[bool] = mapped_column(Boolean, default=False)
    logout_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[AdmUser | None] = relationship()
