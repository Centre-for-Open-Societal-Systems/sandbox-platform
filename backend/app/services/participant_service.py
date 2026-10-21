"""User lifecycle: profile, environment promotion, admin decisions, queries.

Sandbox access needs no administrator - it is granted the moment the email
address is verified. Everything in this module is about the two gates that do
need a human: UAT and production.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.deps import AdminPrincipal
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, apply_search, apply_sort, paginate
from app.core.security import hash_password
from app.models.enums import ApprovalStatus, Environment
from app.models.participant import Participant
from app.repositories.participant_repository import (
    ParticipantQueryRepository,
    ParticipantRepository,
    ParticipantRequestRepository,
    ParticipantTokenRepository,
)
from app.schemas.participant import (
    AdminParticipantDetail,
    AdminQueryOut,
    ParticipantListQuery,
    ParticipantOut,
    PromotionRequestOut,
    QueryListQuery,
)
from app.services import audit_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_templated
from app.utils import exporters

#: Rows written to a single spreadsheet export.
EXPORT_ROW_LIMIT = 5000

#: Everything UAT review needs to see before a decision can be made.
REQUIRED_FOR_UAT = (
    "profile_type",
    "company_name",
    "organization_registration_number",
    "admin_area_code_l1",
    "participant_type_id",
    "service_domain",
    "authorized_person_name",
    "authorized_person_designation",
    "description",
)


def _list(db: Session, query: ParticipantListQuery, stmt) -> Page:
    repo = ParticipantRepository(db)
    stmt = repo.apply_common_filters(stmt, query.model_dump())
    stmt = apply_search(stmt, query.search, repo.search_cols())
    stmt = apply_sort(
        stmt, Participant, query.sort_by, query.sort_dir, repo.default_sort
    )

    page = paginate(db, stmt, query.page, query.limit)
    page.rows = [ParticipantOut.model_validate(row) for row in page.rows]
    return page


def list_users(db: Session, query: ParticipantListQuery) -> Page:
    repo = ParticipantRepository(db)
    return _list(db, query, repo.environment_stmt(query.environment))


def list_pending(
    db: Session, query: ParticipantListQuery, environment: Environment
) -> Page:
    repo = ParticipantRepository(db)
    return _list(db, query, repo.pending_stmt(environment))


def list_rejected(
    db: Session, query: ParticipantListQuery, environment: Environment | None = None
) -> Page:
    repo = ParticipantRepository(db)
    return _list(db, query, repo.rejected_stmt(environment))


def get_user(db: Session, participant_id: int) -> AdminParticipantDetail:
    participant = _require_participant(db, participant_id)
    requests = sorted(
        ParticipantRequestRepository(db).list_all(participant_id=participant_id),
        key=lambda row: row.request_id,
        reverse=True,
    )
    detail = AdminParticipantDetail.model_validate(participant)
    detail.requests = [PromotionRequestOut.model_validate(row) for row in requests]
    return detail


def approve_environment(
    db: Session,
    admin: AdminPrincipal,
    participant_id: int,
    environment: Environment,
    remarks: str | None,
) -> ParticipantOut:
    participant = _require_participant(db, participant_id)
    now = datetime.now(UTC)

    if environment == Environment.UAT:
        participant.is_uat_approved = True
        participant.is_uat_rejected = False
        participant.uat_approved_date = now
    elif environment == Environment.PRODUCTION:
        participant.is_prod_approved = True
        participant.is_prod_enabled = True
        participant.is_prod_rejected = False
        participant.prod_approved_date = now
    else:
        participant.is_sandbox_approved = True
        participant.is_approved = int(ApprovalStatus.APPROVED)
        participant.is_rejected = False
        participant.approved_date = now

    participant.rejection_reason = None
    participant.modify_by = admin.id
    db.commit()

    _close_promotion_request(
        db, participant_id, environment, ApprovalStatus.APPROVED, admin.id, remarks
    )

    send_templated(
        db,
        TemplateCode.PROMOTION_APPROVED,
        participant.email_id,
        {"name": participant.display_name, "environment": str(environment)},
    )
    audit_service.record_admin(
        db,
        admin,
        Action.PARTICIPANT_APPROVE,
        entity="participant",
        entity_id=participant_id,
        description=f"Approved {environment} access for {participant.display_name}",
        country_code=participant.country_code,
    )
    return ParticipantOut.model_validate(participant)


def reject(
    db: Session,
    admin: AdminPrincipal,
    participant_id: int,
    environment: Environment,
    reason: str,
) -> ParticipantOut:
    participant = _require_participant(db, participant_id)

    if environment == Environment.UAT:
        participant.is_uat_approved = False
        participant.is_uat_rejected = True
    elif environment == Environment.PRODUCTION:
        participant.is_prod_approved = False
        participant.is_prod_enabled = False
        participant.is_prod_rejected = True
    else:
        participant.is_sandbox_approved = False
        participant.is_approved = int(ApprovalStatus.REJECTED)
        participant.is_rejected = True

    participant.rejection_reason = reason
    participant.modify_by = admin.id
    db.commit()

    _close_promotion_request(
        db, participant_id, environment, ApprovalStatus.REJECTED, admin.id, reason
    )

    send_templated(
        db,
        TemplateCode.PROMOTION_REJECTED,
        participant.email_id,
        {
            "name": participant.display_name,
            "environment": str(environment),
            "reason": reason,
        },
    )
    audit_service.record_admin(
        db,
        admin,
        Action.PARTICIPANT_REJECT,
        entity="participant",
        entity_id=participant_id,
        description=f"Rejected {environment} access: {reason}",
        country_code=participant.country_code,
    )
    return ParticipantOut.model_validate(participant)


def toggle(
    db: Session, admin: AdminPrincipal, participant_id: int, is_enabled: bool | None
) -> ParticipantOut:
    participant = _require_participant(db, participant_id)
    ParticipantRepository(db).toggle(participant, is_enabled, admin.id)

    if not participant.is_enabled:
        _revoke_sessions(db, participant_id)

    audit_service.record_admin(
        db,
        admin,
        Action.PARTICIPANT_TOGGLE,
        entity="participant",
        entity_id=participant_id,
        description=(
            f"{'Enabled' if participant.is_enabled else 'Disabled'} {participant.display_name}"
        ),
        country_code=participant.country_code,
    )
    return ParticipantOut.model_validate(participant)


def delete(db: Session, admin: AdminPrincipal, participant_id: int) -> None:
    participant = _require_participant(db, participant_id)
    ParticipantRepository(db).soft_delete(participant, admin.id)
    _revoke_sessions(db, participant_id)

    audit_service.record_admin(
        db,
        admin,
        Action.PARTICIPANT_DELETE,
        entity="participant",
        entity_id=participant_id,
        description=f"Deleted participant {participant.display_name}",
        country_code=participant.country_code,
    )


def update_profile(
    db: Session,
    participant: Participant,
    values: dict,
    id_proof_path: str | None = None,
) -> ParticipantOut:
    for field, value in values.items():
        if value is not None and hasattr(participant, field):
            setattr(participant, field, value)
    if id_proof_path:
        participant.id_proof = id_proof_path
    participant.is_profile_complete = profile_is_complete(participant)
    participant.modify_date = datetime.now(UTC)
    db.commit()

    audit_service.record(
        db,
        Action.PARTICIPANT_PROFILE_UPDATE,
        actor_type="participant",
        actor_id=participant.participant_id,
        actor_name=participant.display_name,
        entity="participant",
        entity_id=participant.participant_id,
        country_code=participant.country_code,
    )
    return ParticipantOut.model_validate(participant)


def profile_is_complete(participant: Participant) -> bool:
    """True when every field UAT review depends on has a value."""
    return all(getattr(participant, field, None) for field in REQUIRED_FOR_UAT)


def missing_profile_fields(participant: Participant) -> list[str]:
    return [
        field for field in REQUIRED_FOR_UAT if not getattr(participant, field, None)
    ]


def reset_participant_password(
    db: Session, admin: AdminPrincipal, participant_id: int, new_password: str
) -> None:
    participant = _require_participant(db, participant_id)
    participant.user_pass = hash_password(new_password)
    participant.modify_by = admin.id
    db.commit()
    _revoke_sessions(db, participant_id)


# ------------------------------------------------------- environment promotion
def request_promotion(
    db: Session,
    participant: Participant,
    environment: Environment,
    remarks: str | None,
    extra_data: dict,
    certificate_path: str | None = None,
    document_path: str | None = None,
):
    requests = ParticipantRequestRepository(db)
    if requests.has_open_request(participant.participant_id, environment):
        raise ConflictError(f"A {environment} request is already under review.")

    _assert_promotion_allowed(participant, environment)

    request = requests.create(
        participant_id=participant.participant_id,
        target_environment=str(environment),
        status=int(ApprovalStatus.PENDING),
        remarks=remarks,
        extra_data=extra_data,
        certificate_path=certificate_path,
        document_path=document_path,
        added_by=participant.participant_id,
    )

    if environment == Environment.UAT:
        participant.is_uat_requested = True
        participant.is_uat_rejected = False
    elif environment == Environment.PRODUCTION:
        participant.is_prod_requested = True
        participant.is_prod_rejected = False
    db.commit()

    audit_service.record(
        db,
        Action.PROMOTION_REQUEST,
        actor_type="participant",
        actor_id=participant.participant_id,
        actor_name=participant.display_name,
        entity="participant_request_info",
        entity_id=request.request_id,
        description=f"Requested {environment} access",
        country_code=participant.country_code,
    )
    return request


def promotion_status(db: Session, participant_id: int) -> list:
    return ParticipantRequestRepository(db).list_all(participant_id=participant_id)


def export_participants(
    db: Session, query: ParticipantListQuery, fmt: str
) -> tuple[bytes, str, str]:
    query.limit = EXPORT_ROW_LIMIT
    page = list_users(db, query)
    rows = [row.model_dump() for row in page.rows]
    return exporters.export(rows, exporters.PARTICIPANT_COLUMNS, fmt, "Users")


# ----------------------------------------------------------------- queries
def list_queries(db: Session, query: QueryListQuery) -> Page:
    """Console list of support queries, each with the participant who raised it."""
    repo = ParticipantQueryRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
        stmt=repo.search_stmt(query.search),
        status=query.status,
        query_type=query.query_type,
    )
    # One lookup for the whole page rather than one per row.
    ids = {row.participant_id for row in page.rows if row.participant_id}
    participants = {p.participant_id: p for p in ParticipantRepository(db).get_many(ids)}
    rows = []
    for row in page.rows:
        participant = participants.get(row.participant_id)
        rows.append(
            AdminQueryOut.model_validate(row).model_copy(
                update={
                    "participant_name": participant.full_name if participant else None,
                    "email_id": participant.email_id if participant else None,
                    "company_name": participant.company_name if participant else None,
                }
            )
        )
    page.rows = rows
    return page


def create_query(
    db: Session,
    participant: Participant,
    subject: str,
    description: str,
    query_type: int | None,
):
    return ParticipantQueryRepository(db).create(
        participant_id=participant.participant_id,
        query_type=query_type,
        subject=subject,
        description=description,
        added_by=participant.participant_id,
    )


def respond_to_query(
    db: Session, admin: AdminPrincipal, query_id: int, response: str, status: int
):
    repo = ParticipantQueryRepository(db)
    query = repo.get(query_id)
    if query is None:
        raise NotFoundError("Query not found.")

    query.response = response
    query.status = status
    query.responded_by = admin.id
    query.responded_date = datetime.now(UTC)
    db.commit()

    participant = ParticipantRepository(db).get(query.participant_id)
    if participant is not None and participant.email_id:
        send_templated(
            db,
            TemplateCode.QUERY_RESPONSE,
            participant.email_id,
            {
                "name": participant.display_name,
                "subject": query.subject,
                "response": response,
            },
        )
    return query


# ------------------------------------------------------------------ helpers
def _require_participant(db: Session, participant_id: int) -> Participant:
    participant = ParticipantRepository(db).get(participant_id)
    if participant is None:
        raise NotFoundError("User not found.")
    return participant


def _assert_promotion_allowed(
    participant: Participant, environment: Environment
) -> None:
    if environment == Environment.SANDBOX:
        raise ValidationError("Sandbox access is granted automatically.")

    if not participant.is_email_verified:
        raise ValidationError("Verify your email address before requesting access.")

    if environment == Environment.UAT:
        if not participant.is_sandbox_approved:
            raise ValidationError(
                "Sandbox access must be active before requesting UAT."
            )
        missing = missing_profile_fields(participant)
        if missing:
            raise ValidationError(
                "Complete your profile before requesting UAT access. Missing: "
                + ", ".join(field.replace("_", " ") for field in missing)
                + "."
            )
    elif environment == Environment.PRODUCTION and not participant.is_uat_approved:
        raise ValidationError(
            "UAT access must be approved before requesting production."
        )


def _close_promotion_request(
    db: Session,
    participant_id: int,
    environment: Environment,
    status: ApprovalStatus,
    admin_id: int,
    remarks: str | None,
) -> None:
    request = ParticipantRequestRepository(db).latest_for(participant_id, environment)
    if request is None or request.status != int(ApprovalStatus.PENDING):
        return

    request.status = int(status)
    request.reviewed_by = admin_id
    request.reviewed_date = datetime.now(UTC)
    if status == ApprovalStatus.REJECTED:
        request.rejection_reason = remarks
    else:
        request.remarks = remarks or request.remarks
    db.commit()


def _revoke_sessions(db: Session, participant_id: int) -> None:
    tokens = ParticipantTokenRepository(db)
    for token in tokens.list_all(participant_id=participant_id, is_logout=False):
        tokens.logout(token)
