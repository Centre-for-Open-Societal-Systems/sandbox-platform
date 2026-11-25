"""Who may download a private upload.

Participant documents (ID proof, environment-request certificates) are served
through the same ``/files`` route as public catalogue assets, so the route asks
this module before handing them out. A signed-in administrator may read any of
them; a participant only the files on their own record.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_admin, get_current_participant
from app.core.exceptions import AppError, ForbiddenError, UnauthorizedError
from app.core.permissions import Permission
from app.models.participant import Participant, ParticipantRequestInfo


def assert_can_read(
    db: Session, file_path: str, access_token: str | None, auth_key: str | None
) -> None:
    if not access_token or not auth_key:
        raise UnauthorizedError("Sign in to view this document.")

    # The same checks as every other admin / participant route (token kind,
    # session owner, expiry, blocked account).
    try:
        admin = get_current_admin(db, access_token, auth_key)
    except AppError:
        admin = None
    if admin is not None:
        if admin.can(Permission.ALL_PARTICIPANTS):
            return
        raise ForbiddenError("You do not have access to this document.")

    participant = get_current_participant(db, access_token, auth_key).participant
    if not _owns(db, participant, file_path):
        raise ForbiddenError("You do not have access to this document.")


def _owns(db: Session, participant: Participant, file_path: str) -> bool:
    if participant.id_proof == file_path:
        return True
    stmt = (
        select(ParticipantRequestInfo.request_id)
        .where(ParticipantRequestInfo.participant_id == participant.participant_id)
        .where(
            or_(
                ParticipantRequestInfo.certificate_path == file_path,
                ParticipantRequestInfo.document_path == file_path,
            )
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None
