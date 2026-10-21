"""FastAPI dependencies: authentication, authorisation and request context.

Two audiences - back-office users and network participants - each with their
own guard. Both check the same two headers the reference stack used:

* ``x-access-token`` - the JWT
* ``x-auth-key``     - the opaque session handle, so a signed-out session is
  rejected even while its JWT is still inside its lifetime
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.context import actor_id_ctx, actor_type_ctx
from app.core.database import get_db
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.permissions import Permission
from app.core.security import decode_token
from app.models.admin import AdmUser
from app.models.participant import Participant
from app.repositories.admin_repository import (
    AdminTokenRepository,
    AdminUserRepository,
    PermissionRepository,
)
from app.repositories.participant_repository import (
    ParticipantRepository,
    ParticipantTokenRepository,
)

DbSession = Annotated[Session, Depends(get_db)]

#: Locale used when the request does not ask for a specific one.
DEFAULT_LOCALE = "en"


@dataclass(slots=True)
class AdminPrincipal:
    user: AdmUser
    auth_key: str
    permissions: set[int]

    @property
    def id(self) -> int:
        return self.user.admin_id

    @property
    def is_master(self) -> bool:
        return bool(self.user.is_master)

    @property
    def country_code(self) -> str | None:
        return self.user.country_code

    def can(self, permission: Permission | int) -> bool:
        return self.is_master or int(permission) in self.permissions


@dataclass(slots=True)
class ParticipantPrincipal:
    participant: Participant
    auth_key: str

    @property
    def id(self) -> int:
        return self.participant.participant_id

    @property
    def country_code(self) -> str:
        return self.participant.country_code


def _require_headers(access_token: str | None, auth_key: str | None) -> tuple[str, str]:
    if not access_token:
        raise UnauthorizedError("Access token is required for authentication.")
    if not auth_key:
        raise UnauthorizedError("Auth key is required for authentication.")
    return access_token, auth_key


def get_current_admin(
    db: DbSession,
    x_access_token: Annotated[str | None, Header(alias="x-access-token")] = None,
    x_auth_key: Annotated[str | None, Header(alias="x-auth-key")] = None,
) -> AdminPrincipal:
    access_token, auth_key = _require_headers(x_access_token, x_auth_key)
    decode_token(access_token)  # raises UnauthorizedError when invalid/expired

    token = AdminTokenRepository(db).get_active(auth_key)
    if token is None:
        raise UnauthorizedError("Session is expired or invalid.")

    user = AdminUserRepository(db).get(token.admin_id)
    if user is None or user.is_deleted:
        raise UnauthorizedError("Your account no longer exists.")
    if not user.is_master and not user.is_enabled:
        raise ForbiddenError(
            "Your account has been blocked, contact the system administrator."
        )

    AdminTokenRepository(db).touch(token)

    permissions = PermissionRepository(db).allowed_ids_for_role(user.role_id)
    actor_type_ctx.set("admin")
    actor_id_ctx.set(str(user.admin_id))
    return AdminPrincipal(user=user, auth_key=auth_key, permissions=permissions)


def get_current_participant(
    db: DbSession,
    x_access_token: Annotated[str | None, Header(alias="x-access-token")] = None,
    x_auth_key: Annotated[str | None, Header(alias="x-auth-key")] = None,
) -> ParticipantPrincipal:
    access_token, auth_key = _require_headers(x_access_token, x_auth_key)
    decode_token(access_token)

    token = ParticipantTokenRepository(db).get_active(auth_key)
    if token is None:
        raise UnauthorizedError("Session is expired or invalid.")

    participant = ParticipantRepository(db).get(token.participant_id)
    if participant is None or participant.is_deleted:
        raise UnauthorizedError("Your account no longer exists.")
    if not participant.is_enabled:
        raise ForbiddenError(
            "Your account has been blocked, contact the system administrator."
        )

    ParticipantTokenRepository(db).touch(token)

    actor_type_ctx.set("participant")
    actor_id_ctx.set(str(participant.participant_id))
    return ParticipantPrincipal(participant=participant, auth_key=auth_key)


def require_permission(permission: Permission):
    """Route guard: ``Depends(require_permission(Permission.API_CATALOGUE))``."""

    def _guard(
        admin: Annotated[AdminPrincipal, Depends(get_current_admin)],
    ) -> AdminPrincipal:
        if not admin.can(permission):
            raise ForbiddenError("You do not have permission to access this screen.")
        return admin

    return _guard


def require_any_permission(*permissions: Permission):
    """Route guard passing when the admin holds at least one of ``permissions``."""

    def _guard(
        admin: Annotated[AdminPrincipal, Depends(get_current_admin)],
    ) -> AdminPrincipal:
        if not any(admin.can(permission) for permission in permissions):
            raise ForbiddenError("You do not have permission to access this screen.")
        return admin

    return _guard


def require_master(
    admin: Annotated[AdminPrincipal, Depends(get_current_admin)],
) -> AdminPrincipal:
    if not admin.is_master:
        raise ForbiddenError("This action is restricted to master administrators.")
    return admin


def get_locale(
    accept_language: Annotated[str | None, Header(alias="accept-language")] = None,
) -> str:
    """Resolve the content locale from the request.

    Only the primary language subtag is used, so ``en-GB`` and ``en-US`` both
    resolve to ``en``. A wildcard or unparseable header falls back to the
    default rather than being treated as a locale of its own - some HTTP
    clients send ``Accept-Language: *``, which would otherwise match no
    content at all.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    primary = accept_language.split(",")[0].split(";")[0].strip().lower()
    language = primary.split("-")[0]
    if not language or not language.isalpha():
        return DEFAULT_LOCALE
    return language[:10]


def get_country(
    request: Request,
    x_country_code: Annotated[str | None, Header(alias="x-country-code")] = None,
) -> str:
    """Active member country for this request.

    The header wins; otherwise fall back to the configured default so
    single-country deployments need no client changes.
    """
    if x_country_code and len(x_country_code) == 2:
        return x_country_code.upper()
    query_value = request.query_params.get("country_code")
    if query_value and len(query_value) == 2:
        return query_value.upper()
    return settings.DEFAULT_COUNTRY_CODE


CurrentAdmin = Annotated[AdminPrincipal, Depends(get_current_admin)]
CurrentParticipant = Annotated[ParticipantPrincipal, Depends(get_current_participant)]
MasterAdmin = Annotated[AdminPrincipal, Depends(require_master)]
Locale = Annotated[str, Depends(get_locale)]
CountryCode = Annotated[str, Depends(get_country)]
