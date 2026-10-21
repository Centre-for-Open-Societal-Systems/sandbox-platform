"""Participant management for the back-office console.

Mounted at ``/admin/participants``. Back-office accounts are a different
audience entirely and live under ``/admin/users``.

The list endpoints line up one-to-one with the console tabs:

==============================  ===========================================
Tab                             Endpoint
==============================  ===========================================
All participants                ``POST /admin/participants/list``
UAT approval pending            ``POST /admin/participants/pending?environment=UAT``
UAT participants                ``POST /admin/participants/list?environment=UAT``
UAT rejected                    ``POST /admin/participants/rejected?environment=UAT``
Production approval pending     ``POST /admin/participants/pending?environment=PRODUCTION``
Production participants         ``POST /admin/participants/list?environment=PRODUCTION``
Production rejected             ``POST /admin/participants/rejected?environment=PRODUCTION``
==============================  ===========================================
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.core.deps import (
    AdminPrincipal,
    DbSession,
    require_any_permission,
    require_permission,
)
from app.core.permissions import Permission
from app.core.responses import ok
from app.models.enums import Environment
from app.schemas.common import ToggleRequest
from app.schemas.content import ExportRequest
from app.schemas.participant import (
    ApproveRequest,
    ParticipantListQuery,
    QueryListQuery,
    QueryRespondRequest,
    RejectRequest,
)
from app.services import audit_service, participant_service
from app.services.audit_service import Action

router = APIRouter(prefix="/participants", tags=["Admin / Participants"])

ManageUsers = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.ALL_PARTICIPANTS))
]


@router.post("/list")
def list_users(
    payload: ParticipantListQuery,
    admin: ManageUsers,
    db: DbSession,
    environment: Environment | None = Query(None),
):
    if environment is not None:
        payload.environment = environment
    page = participant_service.list_users(db, payload)
    return ok("Participants loaded.", page.as_dict("participants"))


@router.post("/pending")
def list_pending(
    payload: ParticipantListQuery,
    admin: ManageUsers,
    db: DbSession,
    environment: Environment = Query(Environment.UAT),
):
    """Participants who have requested the environment and await a decision."""
    page = participant_service.list_pending(db, payload, environment)
    return ok(f"{environment} approvals pending.", page.as_dict("participants"))


@router.post("/rejected")
def list_rejected(
    payload: ParticipantListQuery,
    admin: ManageUsers,
    db: DbSession,
    environment: Environment | None = Query(None),
):
    page = participant_service.list_rejected(db, payload, environment)
    return ok("Rejected participants loaded.", page.as_dict("participants"))


@router.get("/{participant_id}")
def get_user(participant_id: int, admin: ManageUsers, db: DbSession):
    return ok(
        "Participant loaded.",
        participant_service.get_user(db, participant_id).model_dump(),
    )


@router.post("/approve")
def approve(payload: ApproveRequest, admin: ManageUsers, db: DbSession):
    participant = participant_service.approve_environment(
        db, admin, payload.participant_id, payload.environment, payload.remarks
    )
    return ok(f"{payload.environment} access approved.", participant.model_dump())


@router.post("/reject")
def reject(payload: RejectRequest, admin: ManageUsers, db: DbSession):
    participant = participant_service.reject(
        db, admin, payload.participant_id, payload.environment, payload.rejection_reason
    )
    return ok(f"{payload.environment} access rejected.", participant.model_dump())


@router.post("/toggle")
def toggle(payload: ToggleRequest, admin: ManageUsers, db: DbSession):
    participant = participant_service.toggle(db, admin, payload.id, payload.is_enabled)
    return ok("Participant status updated.", participant.model_dump())


@router.delete("/{participant_id}")
def delete(participant_id: int, admin: ManageUsers, db: DbSession):
    participant_service.delete(db, admin, participant_id)
    return ok("Participant deleted successfully.")


@router.post("/export")
def export(payload: ExportRequest, admin: ManageUsers, db: DbSession):
    query = ParticipantListQuery(**payload.filters)
    content, media_type, extension = participant_service.export_participants(
        db, query, payload.format
    )

    audit_service.record_admin(
        db,
        admin,
        Action.EXPORT,
        entity="participant",
        description="Exported participant list",
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="participants.{extension}"'
        },
    )


# --------------------------------------------------------------- queries
#: The User Queries screen; admins who manage participants keep their access.
ManageQueries = Annotated[
    AdminPrincipal,
    Depends(require_any_permission(Permission.USER_QUERIES, Permission.ALL_PARTICIPANTS)),
]


@router.post("/queries/list")
def list_queries(payload: QueryListQuery, admin: ManageQueries, db: DbSession):
    page = participant_service.list_queries(db, payload)
    return ok("Queries loaded.", page.as_dict("queries"))


@router.post("/queries/respond")
def respond_to_query(
    payload: QueryRespondRequest, admin: ManageQueries, db: DbSession
):
    participant_service.respond_to_query(
        db, admin, payload.query_id, payload.response, payload.status
    )
    return ok("Response sent successfully.")
