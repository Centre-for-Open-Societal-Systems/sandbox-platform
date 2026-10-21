"""Admin user and role administration."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import AdminPrincipal
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.core.pagination import Page
from app.core.permissions import PERMISSION_TREE
from app.core.security import generate_token_urlsafe, hash_password
from app.models.admin import AdmRole, AdmUser
from app.repositories.admin_repository import (
    AdminTokenRepository,
    AdminUserRepository,
    PermissionRepository,
    RoleRepository,
)
from app.schemas.admin import (
    AdminUserCreate,
    AdminUserListQuery,
    AdminUserOut,
    PermissionNode,
    RoleCreate,
    RoleDetailOut,
    RoleOut,
    RoleUpdate,
)
from app.services import audit_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_templated

MASTER_ROLE_NAME = "Super Administrator"


# --------------------------------------------------------------- admin users
def list_users(db: Session, query: AdminUserListQuery) -> Page:
    repo = AdminUserRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
        role_id=query.role_id,
        is_enabled=query.is_enabled,
        country_code=query.country_code,
    )
    role_names = _role_names(db, [user.role_id for user in page.rows])
    page.rows = [_to_user_out(user, role_names) for user in page.rows]
    return page


def get_user(db: Session, admin_id: int) -> AdminUserOut:
    user = _require_participant(db, admin_id)
    return _to_user_out(user, _role_names(db, [user.role_id]))


def create_user(
    db: Session, admin: AdminPrincipal, payload: AdminUserCreate
) -> AdminUserOut:
    repo = AdminUserRepository(db)
    _assert_login_available(repo, payload.login_name, payload.email_id)

    if RoleRepository(db).get(payload.role_id) is None:
        raise ValidationError("Selected role does not exist.")

    invite_token = None if payload.password else generate_token_urlsafe()
    user = repo.create(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email_id=payload.email_id.lower(),
        mobile_no=payload.mobile_no,
        login_name=payload.login_name,
        login_pass=hash_password(payload.password) if payload.password else None,
        role_id=payload.role_id,
        country_code=payload.country_code or admin.country_code,
        admin_area_code=payload.admin_area_code,
        description=payload.description,
        is_activated=bool(payload.password),
        set_pass_token=invite_token,
        set_pass_token_time=datetime.now(UTC) if invite_token else None,
        added_by=admin.id,
        modify_by=admin.id,
    )

    if invite_token:
        _send_invite(db, user, invite_token)

    audit_service.record_admin(
        db,
        admin,
        Action.ADMIN_USER_CREATE,
        entity="adm_user",
        entity_id=user.admin_id,
        description=f"Created admin user {user.login_name}",
    )
    return _to_user_out(user, _role_names(db, [user.role_id]))


def update_user(db: Session, admin: AdminPrincipal, payload) -> AdminUserOut:
    repo = AdminUserRepository(db)
    user = _require_participant(db, payload.admin_id)

    if payload.login_name and repo.login_name_taken(payload.login_name, user.admin_id):
        raise ConflictError("This username is already taken.")
    if payload.email_id and repo.email_taken(payload.email_id, user.admin_id):
        raise ConflictError("This email address is already registered.")

    repo.update(
        user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email_id=payload.email_id.lower() if payload.email_id else None,
        mobile_no=payload.mobile_no,
        login_name=payload.login_name,
        role_id=payload.role_id,
        country_code=payload.country_code,
        admin_area_code=payload.admin_area_code,
        description=payload.description,
        modify_by=admin.id,
    )

    if payload.password:
        # A password set by an administrator also completes a pending invite.
        repo.set_fields(
            user,
            login_pass=hash_password(payload.password),
            set_pass_token=None,
            set_pass_token_time=None,
            is_activated=True,
            activate_date=user.activate_date or datetime.now(UTC),
        )

    audit_service.record_admin(
        db,
        admin,
        Action.ADMIN_USER_UPDATE,
        entity="adm_user",
        entity_id=user.admin_id,
        description=f"Updated admin user {user.login_name}",
    )
    return _to_user_out(user, _role_names(db, [user.role_id]))


def toggle_user(
    db: Session, admin: AdminPrincipal, admin_id: int, is_enabled: bool | None
) -> AdminUserOut:
    user = _require_participant(db, admin_id)
    _assert_not_self(admin, user, "You cannot disable your own account.")

    AdminUserRepository(db).toggle(user, is_enabled, admin.id)
    if not user.is_enabled:
        AdminTokenRepository(db).logout_all(user.admin_id)

    audit_service.record_admin(
        db,
        admin,
        Action.ADMIN_USER_TOGGLE,
        entity="adm_user",
        entity_id=user.admin_id,
        description=f"{'Enabled' if user.is_enabled else 'Disabled'} {user.login_name}",
    )
    return _to_user_out(user, _role_names(db, [user.role_id]))


def delete_user(db: Session, admin: AdminPrincipal, admin_id: int) -> None:
    user = _require_participant(db, admin_id)
    _assert_not_self(admin, user, "You cannot delete your own account.")
    if user.is_master:
        raise ForbiddenError("Master administrator accounts cannot be deleted.")

    AdminUserRepository(db).soft_delete(user, admin.id)
    AdminTokenRepository(db).logout_all(user.admin_id)

    audit_service.record_admin(
        db,
        admin,
        Action.ADMIN_USER_DELETE,
        entity="adm_user",
        entity_id=user.admin_id,
        description=f"Deleted admin user {user.login_name}",
    )


def resend_invite(db: Session, admin: AdminPrincipal, admin_id: int) -> None:
    user = _require_participant(db, admin_id)
    token = generate_token_urlsafe()
    user.set_pass_token = token
    user.set_pass_token_time = datetime.now(UTC)
    user.modify_by = admin.id
    db.commit()

    _send_invite(db, user, token)
    audit_service.record_admin(
        db,
        admin,
        Action.ADMIN_USER_INVITE,
        entity="adm_user",
        entity_id=user.admin_id,
        description=f"Re-sent invitation to {user.email_id}",
    )


def is_login_available(
    db: Session, login_name: str, exclude_admin_id: int | None = None
) -> bool:
    return not AdminUserRepository(db).login_name_taken(login_name, exclude_admin_id)


# --------------------------------------------------------------------- roles
def list_roles(db: Session, query) -> Page:
    repo = RoleRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
    )
    role_ids = [role.role_id for role in page.rows]
    grants = PermissionRepository(db).allowed_ids_for_roles(role_ids)
    user_counts = repo.user_counts(role_ids)

    page.rows = [
        RoleDetailOut(
            **RoleOut.model_validate(role).model_dump(),
            permission_ids=sorted(grants.get(role.role_id, set())),
            user_count=user_counts.get(role.role_id, 0),
        )
        for role in page.rows
    ]
    return page


def get_role(db: Session, role_id: int) -> RoleDetailOut:
    role = _require_role(db, role_id)
    return RoleDetailOut(
        **RoleOut.model_validate(role).model_dump(),
        permission_ids=sorted(
            PermissionRepository(db).allowed_ids_for_role(role.role_id)
        ),
        user_count=RoleRepository(db).user_count(role.role_id),
    )


def create_role(
    db: Session, admin: AdminPrincipal, payload: RoleCreate
) -> RoleDetailOut:
    repo = RoleRepository(db)
    if repo.name_taken(payload.role_name):
        raise ConflictError("A role with this name already exists.")

    role = repo.create(
        role_name=payload.role_name.strip(),
        role_level=payload.role_level,
        checker_maker=payload.checker_maker,
        added_by=admin.id,
        modify_by=admin.id,
    )
    PermissionRepository(db).replace_role_permissions(
        role.role_id, payload.permission_ids, admin.id
    )

    audit_service.record_admin(
        db,
        admin,
        Action.ROLE_CREATE,
        entity="adm_role",
        entity_id=role.role_id,
        description=f"Created role {role.role_name}",
    )
    return get_role(db, role.role_id)


def update_role(
    db: Session, admin: AdminPrincipal, payload: RoleUpdate
) -> RoleDetailOut:
    repo = RoleRepository(db)
    role = _require_role(db, payload.role_id)
    if not role.is_editable:
        raise ForbiddenError("This role is system-managed and cannot be edited.")
    if payload.role_name and repo.name_taken(payload.role_name, role.role_id):
        raise ConflictError("A role with this name already exists.")

    repo.update(
        role,
        role_name=payload.role_name.strip() if payload.role_name else None,
        role_level=payload.role_level,
        checker_maker=payload.checker_maker,
        modify_by=admin.id,
    )
    PermissionRepository(db).replace_role_permissions(
        role.role_id, payload.permission_ids, admin.id
    )

    audit_service.record_admin(
        db,
        admin,
        Action.ROLE_UPDATE,
        entity="adm_role",
        entity_id=role.role_id,
        description=f"Updated role {role.role_name}",
    )
    return get_role(db, role.role_id)


def toggle_role(
    db: Session, admin: AdminPrincipal, role_id: int, is_enabled: bool | None
) -> RoleDetailOut:
    role = _require_role(db, role_id)
    RoleRepository(db).toggle(role, is_enabled, admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.ROLE_TOGGLE,
        entity="adm_role",
        entity_id=role.role_id,
        description=f"{'Enabled' if role.is_enabled else 'Disabled'} role {role.role_name}",
    )
    return get_role(db, role_id)


def delete_role(db: Session, admin: AdminPrincipal, role_id: int) -> None:
    repo = RoleRepository(db)
    role = _require_role(db, role_id)
    if not role.is_editable:
        raise ForbiddenError("This role is system-managed and cannot be deleted.")
    if repo.user_count(role_id) > 0:
        raise ConflictError("This role is assigned to users and cannot be deleted.")

    repo.soft_delete(role, admin.id)
    audit_service.record_admin(
        db,
        admin,
        Action.ROLE_DELETE,
        entity="adm_role",
        entity_id=role_id,
        description=f"Deleted role {role.role_name}",
    )


def role_dropdown(db: Session) -> list[dict]:
    return [
        {"label": role.role_name, "value": role.role_id}
        for role in RoleRepository(db).dropdown()
    ]


# --------------------------------------------------------------- permissions
def permission_tree(db: Session, role_id: int | None) -> list[PermissionNode]:
    """Permission catalogue as a two-level tree with the role's grants applied."""
    allowed = PermissionRepository(db).allowed_ids_for_role(role_id)
    nodes = {
        int(pid): PermissionNode(
            permission_id=int(pid),
            menu_name=label,
            parent_id=int(parent) if parent else None,
            has_submenu=has_sub,
            is_allowed=int(pid) in allowed,
        )
        for pid, (label, parent, has_sub) in PERMISSION_TREE.items()
    }

    roots: list[PermissionNode] = []
    for node in nodes.values():
        parent = nodes.get(node.parent_id) if node.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


def update_permissions(
    db: Session, admin: AdminPrincipal, role_id: int, flags: list
) -> None:
    role = _require_role(db, role_id)
    granted = [flag.id for flag in flags if flag.status]
    PermissionRepository(db).replace_role_permissions(role_id, granted, admin.id)

    audit_service.record_admin(
        db,
        admin,
        Action.PERMISSION_UPDATE,
        entity="adm_role",
        entity_id=role_id,
        description=f"Updated permissions for role {role.role_name}",
        changes={"granted": granted},
    )


# ------------------------------------------------------------------ helpers
def _require_participant(db: Session, admin_id: int) -> AdmUser:
    user = AdminUserRepository(db).get(admin_id)
    if user is None:
        raise NotFoundError("Admin user not found.")
    return user


def _require_role(db: Session, role_id: int) -> AdmRole:
    role = RoleRepository(db).get(role_id)
    if role is None:
        raise NotFoundError("Role not found.")
    return role


def _assert_login_available(
    repo: AdminUserRepository, login_name: str, email_id: str
) -> None:
    if repo.login_name_taken(login_name):
        raise ConflictError("This username is already taken.")
    if repo.email_taken(email_id):
        raise ConflictError("This email address is already registered.")


def _assert_not_self(admin: AdminPrincipal, user: AdmUser, message: str) -> None:
    if admin.id == user.admin_id:
        raise ForbiddenError(message)


def _role_names(db: Session, role_ids: list[int | None]) -> dict[int, str]:
    """Resolve role names in one query, so grids do not trigger an N+1."""
    ids = {role_id for role_id in role_ids if role_id}
    if not ids:
        return {}
    rows = db.execute(
        select(AdmRole.role_id, AdmRole.role_name).where(AdmRole.role_id.in_(ids))
    ).all()
    return {int(role_id): name for role_id, name in rows}


def _to_user_out(user: AdmUser, role_names: dict[int, str]) -> AdminUserOut:
    out = AdminUserOut.model_validate(user)
    out.role_name = role_names.get(user.role_id) if user.role_id else None
    return out


def _send_invite(db: Session, user: AdmUser, token: str) -> None:
    send_templated(
        db,
        TemplateCode.ADMIN_INVITE,
        user.email_id,
        {"name": user.full_name or user.login_name, "token": token},
    )
