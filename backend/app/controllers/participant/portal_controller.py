"""Portal: profile, dashboard, promotion requests, support queries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import ValidationError as PydanticValidationError

from app.core.deps import CurrentParticipant, DbSession
from app.core.exceptions import ValidationError
from app.core.responses import ok
from app.models.enums import Environment
from app.repositories.participant_repository import ParticipantQueryRepository
from app.schemas.participant import (
    ParticipantOut,
    ProfileForm,
    PromotionDetails,
    PromotionRequestOut,
    QueryCreate,
    QueryOut,
)
from app.services import log_service, participant_service
from app.services.participant_auth_service import available_environments
from app.utils.files import save_upload

router = APIRouter(tags=["User / Portal"])

ID_PROOF_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
#: Public certificates only - a private key (.key) is never accepted.
CERTIFICATE_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "pem", "crt", "cer"}
DOCUMENT_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}


@router.get("/profile")
def get_profile(current: CurrentParticipant):
    return ok(
        "Profile loaded.",
        ParticipantOut.model_validate(current.participant).model_dump(),
    )


@router.put("/profile")
async def update_profile(
    current: CurrentParticipant,
    db: DbSession,
    payload: Annotated[ProfileForm, Form()],
):
    stored = (
        await save_upload(
            payload.id_proof, "participants/id-proof", ID_PROOF_EXTENSIONS
        )
        if payload.id_proof
        else None
    )
    values = payload.model_dump(exclude={"id_proof"}, exclude_none=True)
    updated = participant_service.update_profile(
        db, current.participant, values, stored.path if stored else None
    )
    return ok("Profile updated successfully.", updated.model_dump())


@router.get("/profile/completeness")
def profile_completeness(current: CurrentParticipant):
    """What the participant still owes us before UAT access can be requested."""
    missing = participant_service.missing_profile_fields(current.participant)
    return ok(
        "Profile completeness loaded.",
        {"is_complete": not missing, "missing_fields": missing},
    )


@router.get("/dashboard")
def dashboard(current: CurrentParticipant, db: DbSession):
    data = log_service.participant_dashboard(db, current.id)
    data["environments"] = available_environments(current.participant)
    data["is_profile_complete"] = current.participant.is_profile_complete
    return ok("Dashboard loaded.", data)


@router.post("/promotion-requests")
async def request_promotion(
    current: CurrentParticipant,
    db: DbSession,
    target_environment: Environment = Form(...),
    remarks: str | None = Form(None),
    certificate: UploadFile | None = File(None),
    document: UploadFile | None = File(None),
    extra_data: str | None = Form(
        None, description="JSON object of the move-to-production questionnaire."
    ),
):
    details = _parse_promotion_details(extra_data)
    certificate_path = (
        (
            await save_upload(
                certificate, "participants/certificates", CERTIFICATE_EXTENSIONS
            )
        ).path
        if certificate
        else None
    )
    document_path = (
        (
            await save_upload(
                document, "participants/documents", DOCUMENT_EXTENSIONS
            )
        ).path
        if document
        else None
    )

    request = participant_service.request_promotion(
        db,
        current.participant,
        target_environment,
        remarks,
        details,
        certificate_path,
        document_path,
    )
    return ok(
        f"{target_environment} access request submitted.",
        {"request_id": request.request_id, "status": request.status},
    )


@router.get("/promotion-requests")
def promotion_status(current: CurrentParticipant, db: DbSession):
    requests = participant_service.promotion_status(db, current.id)
    return ok(
        "Requests loaded.",
        [PromotionRequestOut.model_validate(row).model_dump() for row in requests],
    )


@router.post("/queries")
def create_query(payload: QueryCreate, current: CurrentParticipant, db: DbSession):
    query = participant_service.create_query(
        db,
        current.participant,
        payload.subject,
        payload.description,
        payload.query_type,
    )
    return ok(
        "Your query has been submitted.",
        QueryOut.model_validate(query).model_dump(),
    )


@router.get("/queries")
def list_queries(current: CurrentParticipant, db: DbSession):
    rows = ParticipantQueryRepository(db).list_all(participant_id=current.id)
    return ok(
        "Queries loaded.",
        [QueryOut.model_validate(row).model_dump() for row in rows],
    )


def _parse_promotion_details(raw: str | None) -> dict:
    if not raw or not raw.strip():
        return {}
    try:
        details = PromotionDetails.model_validate_json(raw)
    except PydanticValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(part) for part in first.get("loc", ())) or "extra_data"
        raise ValidationError(f"Invalid {field}: {first.get('msg')}") from exc
    return details.model_dump(exclude_none=True, exclude_defaults=True)
