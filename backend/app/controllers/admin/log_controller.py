"""Audit log and API history screens."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from app.core.deps import AdminPrincipal, DbSession, require_permission
from app.core.exceptions import NotFoundError
from app.core.permissions import Permission
from app.core.responses import ok
from app.schemas.content import ApiLogQuery, ExportRequest, UserActionLogQuery
from app.services import audit_service, log_service
from app.services.audit_service import Action

router = APIRouter(prefix="/logs", tags=["Admin / Audit"])

ViewApiHistory = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.API_HISTORY))
]
ViewUserTracking = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.USER_TRACKING))
]


@router.post("/api-history")
def api_history(payload: ApiLogQuery, admin: ViewApiHistory, db: DbSession):
    return ok(
        "API history loaded.", log_service.list_api_logs(db, payload).as_dict("logs")
    )


@router.get("/api-history/{log_id}")
def api_history_detail(log_id: int, admin: ViewApiHistory, db: DbSession):
    log = log_service.get_api_log(db, log_id)
    if log is None:
        raise NotFoundError("Log entry not found.")
    return ok("Log entry loaded.", log.model_dump())


@router.post("/api-history/export")
def export_api_history(payload: ExportRequest, admin: ViewApiHistory, db: DbSession):
    query = ApiLogQuery(**payload.filters)
    content, media_type, extension = log_service.export_api_logs(
        db, query, payload.format
    )

    audit_service.record_admin(
        db, admin, Action.EXPORT, entity="api_log", description="Exported API history"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="api-history.{extension}"'
        },
    )


@router.post("/user-tracking")
def user_tracking(payload: UserActionLogQuery, admin: ViewUserTracking, db: DbSession):
    return ok(
        "User activity loaded.",
        log_service.list_user_action_logs(db, payload).as_dict("logs"),
    )


@router.post("/user-tracking/export")
def export_user_tracking(
    payload: ExportRequest, admin: ViewUserTracking, db: DbSession
):
    query = UserActionLogQuery(**payload.filters)
    content, media_type, extension = log_service.export_user_action_logs(
        db, query, payload.format
    )

    audit_service.record_admin(
        db,
        admin,
        Action.EXPORT,
        entity="user_action_log",
        description="Exported user tracking",
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="user-tracking.{extension}"'
        },
    )
