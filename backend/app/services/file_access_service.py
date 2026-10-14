"""Who may download a private upload.

Participant documents (ID proof, environment-request certificates) are served
through the same ``/files`` route as public catalogue assets, so the route asks
this module before handing them out. A signed-in administrator may read any of
them; a participant only the files on their own record.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.models.participant import Participant, ParticipantRequestInfo
from app.repositories.admin_repository import AdminTokenRepository, AdminUserRepository
from app.repositories.participant_repository import (
    ParticipantRepository,
    ParticipantTokenRepository,
)


def assert_can_read(
    db: Session, file_path: str, access_token: str | None, auth_key: str | None
) -> None:
    if not access_token or not auth_key:
        raise UnauthorizedError("Sign in to view this document.")
    decode_token(access_token)  # raises when invalid or expired

    admin_token = AdminTokenRepository(db).get_active(auth_key)
    if admin_token is not None:
        admin = AdminUserRepository(db).get(admin_token.admin_id)
        if admin is not None and (admin.is_master or admin.is_enabled):
            return
        raise UnauthorizedError("Session is expired or invalid.")

    participant_token = ParticipantTokenRepository(db).get_active(auth_key)
    if participant_token is None:
        raise UnauthorizedError("Session is expired or invalid.")
    participant = ParticipantRepository(db).get(participant_token.participant_id)
    if participant is None or not _owns(db, participant, file_path):
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
