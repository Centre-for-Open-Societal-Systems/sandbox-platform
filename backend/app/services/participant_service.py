"""User lifecycle: profile, environment promotion, admin decisions, queries.

Two gates, each decided by an administrator: UAT and production. Signing up
is the UAT request (reviewed on the sign-up details alone); approving it opens
the portal. Production is requested from the portal with a complete profile.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.context import admin_country_scope, assert_in_admin_scope
from app.core.deps import AdminPrincipal
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, apply_search, apply_sort, paginate
from app.core.security import hash_password
from app.models.enums import ActivationStatus, ApprovalStatus, Environment
from app.models.participant import Participant
from app.repositories.participant_repository import (
    ParticipantRepository,
    ParticipantRequestRepository,
    ParticipantTokenRepository,
)
from app.schemas.participant import (
    AdminParticipantDetail,
    ParticipantListQuery,
    ParticipantOut,
    PromotionRequestOut,
)
from app.services import app_gateway_service, audit_service, iam_user_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_templated
from app.utils import exporters

#: Rows written to a single spreadsheet export.
EXPORT_ROW_LIMIT = 5000

#: Everything production review needs to see before a decision can be made.
REQUIRED_FOR_PRODUCTION = (
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
    if (scope := admin_country_scope()) is not None:
        stmt = stmt.where(Participant.country_code == scope)
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

    if environment == Environment.PRODUCTION:
        # The signing key the request carried becomes the partner's key (its JWKS).
        request = ParticipantRequestRepository(db).latest_for(participant_id, environment)
        if request is not None and request.status == int(ApprovalStatus.PENDING):
            key = (request.extra_data or {}).get("public_key")
            if key and "BEGIN PUBLIC KEY" in key:
                participant.public_key = key
        participant.is_prod_approved = True
        participant.is_prod_enabled = True
        participant.is_prod_rejected = False
        participant.prod_approved_date = now
    else:
        # UAT approval is the account approval: the participant may sign in.
        participant.is_uat_approved = True
        participant.is_uat_rejected = False
        participant.uat_approved_date = now
        participant.is_approved = int(ApprovalStatus.APPROVED)
        participant.is_rejected = False
        participant.approved_date = now
        # Sign-ups made while mail is off have no code to enter: approval verifies them.
        participant.is_email_verified = True
        participant.otp = None
        if participant.is_activated != int(ActivationStatus.BLOCKED):
            participant.is_activated = int(ActivationStatus.ACTIVATED)
            participant.activated_date = participant.activated_date or now

    participant.rejection_reason = None
    participant.modify_by = admin.id
    db.commit()

    _close_promotion_request(
        db, participant_id, environment, ApprovalStatus.APPROVED, admin.id, remarks
    )
    # The first approval creates the Keycloak user (no password yet: the
    # participant's next portal sign-in hands it over); later ones add roles.
    iam_user_service.sync(db, participant, actor_id=admin.id)
    app_gateway_service.sync_participant_apps(db, participant_id)

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

    if environment == Environment.PRODUCTION:
        participant.is_prod_approved = False
        participant.is_prod_enabled = False
        participant.is_prod_rejected = True
    else:
        # No UAT means no account: production goes with it.
        participant.is_uat_approved = False
        participant.is_uat_rejected = True
        participant.is_prod_approved = False
        participant.is_prod_enabled = False
        participant.is_approved = int(ApprovalStatus.REJECTED)
        participant.is_rejected = True

    participant.rejection_reason = reason
    participant.modify_by = admin.id
    db.commit()

    _close_promotion_request(
        db, participant_id, environment, ApprovalStatus.REJECTED, admin.id, reason
    )
    if environment == Environment.UAT:
        # No access any more: sign them out and stop their keys.
        _revoke_sessions(db, participant_id)
    iam_user_service.sync(db, participant, actor_id=admin.id)
    app_gateway_service.sync_participant_apps(db, participant_id)

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
    iam_user_service.sync(db, participant, actor_id=admin.id)
    app_gateway_service.sync_participant_apps(db, participant_id)

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
    iam_user_service.sync(db, participant, actor_id=admin.id)
    app_gateway_service.sync_participant_apps(db, participant_id)

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
    """True when every field production review depends on has a value."""
    return all(getattr(participant, field, None) for field in REQUIRED_FOR_PRODUCTION)


def missing_profile_fields(participant: Participant) -> list[str]:
    return [
        field
        for field in REQUIRED_FOR_PRODUCTION
        if not getattr(participant, field, None)
    ]


def reset_participant_password(
    db: Session, admin: AdminPrincipal, participant_id: int, new_password: str
) -> None:
    participant = _require_participant(db, participant_id)
    participant.user_pass = hash_password(new_password)
    participant.modify_by = admin.id
    _revoke_sessions(db, participant_id)
    db.commit()
    _revoke_sessions(db, participant_id)
    iam_user_service.sync(db, participant, password=new_password, actor_id=admin.id)


# ------------------------------------------------------- environment promotion
def assert_promotion_possible(db: Session, participant: Participant, environment: Environment) -> None:
    """Raise when the participant cannot ask for ``environment`` now (open request, profile, UAT)."""
    if ParticipantRequestRepository(db).has_open_request(participant.participant_id, environment):
        raise ConflictError(f"A {environment} request is already under review.")
    _assert_promotion_allowed(participant, environment)


def request_promotion(
    db: Session,
    participant: Participant,
    environment: Environment,
    remarks: str | None,
    extra_data: dict,
    certificate_path: str | None = None,
    document_path: str | None = None,
):
    assert_promotion_possible(db, participant, environment)
    request = ParticipantRequestRepository(db).create(
        participant_id=participant.participant_id,
        target_environment=str(environment),
        status=int(ApprovalStatus.PENDING),
        remarks=remarks,
        extra_data=extra_data,
        certificate_path=certificate_path,
        document_path=document_path,
        added_by=participant.participant_id,
    )

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


# ------------------------------------------------------------------ helpers
def _require_participant(db: Session, participant_id: int) -> Participant:
    participant = ParticipantRepository(db).get(participant_id)
    # Another country's participant is "not found" for a country administrator.
    if participant is None or not assert_in_admin_scope(participant.country_code):
        raise NotFoundError("User not found.")
    return participant


def _assert_promotion_allowed(
    participant: Participant, environment: Environment
) -> None:
    if environment == Environment.UAT:
        raise ValidationError(
            "UAT access is requested by signing up and reviewed by an administrator."
        )

    if not participant.is_email_verified:
        raise ValidationError("Verify your email address before requesting access.")

    if not participant.is_uat_approved:
        raise ValidationError(
            "UAT access must be approved before requesting production."
        )
    missing = missing_profile_fields(participant)
    if missing:
        raise ValidationError(
            "Complete your profile before requesting production access. Missing: "
            + ", ".join(field.replace("_", " ") for field in missing)
            + "."
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
    ParticipantTokenRepository(db).logout_all(participant_id)
