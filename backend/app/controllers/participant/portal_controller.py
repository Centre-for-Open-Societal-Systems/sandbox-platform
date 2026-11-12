"""Portal: profile, dashboard, promotion requests, support queries."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import ValidationError as PydanticValidationError

from app.core.deps import CurrentParticipant, DbSession
from app.core.exceptions import ValidationError
from app.core.responses import ok
from app.models.enums import Environment
from app.schemas.participant import (
    ParticipantOut,
    ProfileForm,
    PromotionDetails,
    PromotionRequestOut,
    QueryCreate,
    QueryMessageCreate,
)
from app.services import (
    log_service,
    participant_data_export_service,
    participant_service,
    support_service,
)
from app.services.participant_auth_service import available_environments
from app.utils import partner_keys
from app.utils.files import save_upload, validate_upload

router = APIRouter(tags=["User / Portal"])

ID_PROOF_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
#: X.509 certificates only (PEM or DER) - a private key (.key) is never accepted.
CERTIFICATE_EXTENSIONS = partner_keys.CERTIFICATE_EXTENSIONS
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


@router.get("/profile/export")
def export_my_data(current: CurrentParticipant, db: DbSession):
    """The participant's own data (profile, apps without keys, queries, call history) as JSON."""
    return ok("Your data.", participant_data_export_service.export_participant_data(db, current))


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
    # File types first (as before), then who may ask (profile, UAT, an open request),
    # then the key.
    if certificate:
        validate_upload(certificate, CERTIFICATE_EXTENSIONS)
    if document:
        validate_upload(document, DOCUMENT_EXTENSIONS)
    participant_service.assert_promotion_possible(db, current.participant, target_environment)
    if target_environment == Environment.PRODUCTION:
        # The partner's signing key: from the certificate, or the pasted public key.
        certificate_bytes = None
        if certificate:
            certificate_bytes = await certificate.read()
            await certificate.seek(0)
        key = partner_keys.partner_key(certificate_bytes, details.get("public_key"))
        details["public_key"] = key.public_key
        details["key"] = key.details()
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
    query = support_service.create_ticket(
        db, current, payload.subject, payload.description, payload.query_type
    )
    return ok("Your query has been submitted.", query.model_dump())


@router.get("/queries")
def list_queries(current: CurrentParticipant, db: DbSession):
    rows = support_service.list_for_participant(db, current.id)
    return ok("Queries loaded.", [row.model_dump() for row in rows])


@router.get("/queries/{query_id}")
def query_thread(query_id: int, current: CurrentParticipant, db: DbSession):
    """One ticket with its conversation (staff notes are never included)."""
    return ok("Ticket loaded.", support_service.participant_thread(db, current.participant, query_id).model_dump())


@router.post("/queries/{query_id}/messages")
def reply_to_query(
    query_id: int, payload: QueryMessageCreate, current: CurrentParticipant, db: DbSession
):
    thread = support_service.participant_reply(db, current, query_id, payload.body)
    return ok("Your reply has been sent.", thread.model_dump())


@router.post("/queries/{query_id}/close")
def close_query(query_id: int, current: CurrentParticipant, db: DbSession):
    """The participant marks the ticket resolved."""
    return ok("Ticket closed.", support_service.participant_close(db, current, query_id).model_dump())


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
