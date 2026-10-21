"""Back-office user, role and permission management.

Mounted at ``/admin/users`` and ``/admin/roles``. Network participants are a
different domain entirely and live under ``/admin/participants``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import AdminPrincipal, DbSession, require_permission
from app.core.permissions import Permission
from app.core.responses import ok
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserListQuery,
    AdminUserUpdate,
    PermissionUpdateRequest,
    RoleCreate,
    RoleUpdate,
)
from app.schemas.common import ListQuery, ToggleRequest
from app.services import admin_user_service

router = APIRouter(tags=["Admin / Users & Roles"])

ManageUsers = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.AUM_VIEW_USER_LIST))
]
ManageRoles = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.AUM_MANAGE_ROLES))
]


# ---------------------------------------------------------------- users
@router.post("/users/list")
def list_users(payload: AdminUserListQuery, admin: ManageUsers, db: DbSession):
    return ok(
        "Users loaded.",
        admin_user_service.list_users(db, payload).as_dict("users"),
    )


@router.get("/users/{admin_id}")
def get_user(admin_id: int, admin: ManageUsers, db: DbSession):
    return ok(
        "User loaded.",
        admin_user_service.get_user(db, admin_id).model_dump(),
    )


@router.post("/users")
def create_user(payload: AdminUserCreate, admin: ManageUsers, db: DbSession):
    user = admin_user_service.create_user(db, admin, payload)
    return ok("User created successfully.", user.model_dump())


@router.put("/users")
def update_user(payload: AdminUserUpdate, admin: ManageUsers, db: DbSession):
    user = admin_user_service.update_user(db, admin, payload)
    return ok("User updated successfully.", user.model_dump())


@router.post("/users/toggle")
def toggle_user(payload: ToggleRequest, admin: ManageUsers, db: DbSession):
    user = admin_user_service.toggle_user(db, admin, payload.id, payload.is_enabled)
    return ok("User status updated.", user.model_dump())


@router.delete("/users/{admin_id}")
def delete_user(admin_id: int, admin: ManageUsers, db: DbSession):
    admin_user_service.delete_user(db, admin, admin_id)
    return ok("User deleted successfully.")


@router.post("/users/{admin_id}/invite")
def resend_invite(admin_id: int, admin: ManageUsers, db: DbSession):
    admin_user_service.resend_invite(db, admin, admin_id)
    return ok("Invitation sent successfully.")


# ---------------------------------------------------------------- roles
@router.post("/roles/list")
def list_roles(payload: ListQuery, admin: ManageRoles, db: DbSession):
    return ok(
        "Roles loaded.", admin_user_service.list_roles(db, payload).as_dict("roles")
    )


@router.get("/roles/dropdown")
def role_dropdown(admin: ManageUsers, db: DbSession):
    return ok("Roles loaded.", admin_user_service.role_dropdown(db))


@router.get("/roles/{role_id}")
def get_role(role_id: int, admin: ManageRoles, db: DbSession):
    return ok("Role loaded.", admin_user_service.get_role(db, role_id).model_dump())


@router.post("/roles")
def create_role(payload: RoleCreate, admin: ManageRoles, db: DbSession):
    role = admin_user_service.create_role(db, admin, payload)
    return ok("Role created successfully.", role.model_dump())


@router.put("/roles")
def update_role(payload: RoleUpdate, admin: ManageRoles, db: DbSession):
    role = admin_user_service.update_role(db, admin, payload)
    return ok("Role updated successfully.", role.model_dump())


@router.post("/roles/toggle")
def toggle_role(payload: ToggleRequest, admin: ManageRoles, db: DbSession):
    role = admin_user_service.toggle_role(db, admin, payload.id, payload.is_enabled)
    return ok("Role status updated.", role.model_dump())


@router.delete("/roles/{role_id}")
def delete_role(role_id: int, admin: ManageRoles, db: DbSession):
    admin_user_service.delete_role(db, admin, role_id)
    return ok("Role deleted successfully.")


# ---------------------------------------------------------- permissions
@router.get("/permissions")
def permissions(admin: ManageRoles, db: DbSession, role_id: int | None = None):
    tree = admin_user_service.permission_tree(db, role_id)
    return ok("Permissions loaded.", [node.model_dump() for node in tree])


@router.put("/permissions")
def update_permissions(
    payload: PermissionUpdateRequest, admin: ManageRoles, db: DbSession
):
    admin_user_service.update_permissions(
        db, admin, payload.role_id, payload.permissions
    )
    return ok("Permissions updated successfully.")
