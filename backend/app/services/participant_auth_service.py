"""Portal registration and authentication.

Registration is deliberately short: one form, then an emailed code. Verifying
the code activates the account and grants sandbox access immediately - no
administrator is in the loop. Organisation details are collected later, and
only reviewed when the participant asks for UAT or production access.

That split is the reason the reference stack's ``temp_customer`` staging table
is gone: there is no longer a window in which a registration exists but an
account does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.context import client_ip_ctx
from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    generate_token_urlsafe,
    hash_password,
    verify_password,
)
from app.models.enums import ActivationStatus, ApprovalStatus, Environment
from app.models.participant import Participant
from app.repositories.participant_repository import (
    ParticipantRepository,
    ParticipantTokenRepository,
)
from app.schemas.participant import ParticipantLoginResponse, SignupRequest
from app.services import audit_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_otp, send_templated
from app.utils.common import mask_email

INVALID_CREDENTIALS = "No such email address or password."
RESET_TOKEN_TTL_HOURS = 2


def signup(db: Session, payload: SignupRequest) -> dict:
    """Create the account and email the verification code.

    The row is written unverified. Nothing but the verification step is
    possible until the code is entered.
    """
    participants = ParticipantRepository(db)
    if participants.email_taken(payload.email_id):
        raise ConflictError("An account with this email address already exists.")

    otp = generate_otp()
    participant = participants.create(
        first_name=payload.first_name,
        last_name=payload.last_name,
        email_id=payload.email_id.lower(),
        mobile_number=payload.mobile_number,
        company_name=payload.company_name,
        category_id=payload.category_id,
        user_pass=hash_password(payload.password),
        country_code=payload.country_code,
        declaration=payload.declaration,
        otp=otp,
        otp_generated_at=datetime.now(UTC),
        otp_request_count=1,
        ip_address=client_ip_ctx.get() or None,
    )

    send_otp(db, otp, email=participant.email_id)
    audit_service.record(
        db,
        Action.PARTICIPANT_SIGNUP,
        actor_type="participant",
        actor_name=participant.display_name,
        entity="participant",
        entity_id=participant.participant_id,
        country_code=participant.country_code,
    )

    return {
        "unique_id": participant.unique_id,
        "masked_email": mask_email(participant.email_id),
        "otp_validity_seconds": settings.OTP_TTL_SECONDS,
        # True while mail is off: the code is DEV_FIXED_OTP, not an emailed one.
        "is_fixed_otp": bool(settings.fixed_otp),
    }


def verify_email(db: Session, unique_id: str, otp: str) -> dict:
    """Confirm the emailed code, then activate the account.

    Sandbox access is granted here. UAT and production stay closed until an
    administrator approves a promotion request.
    """
    participant = _require_participant(db, unique_id)

    if participant.is_email_verified:
        return {"unique_id": participant.unique_id, "already_verified": True}
    if not participant.otp or participant.otp != otp:
        raise ValidationError("The verification code is incorrect.")
    if _otp_expired(participant.otp_generated_at):
        raise ValidationError(
            "The verification code has expired, please request a new one."
        )

    now = datetime.now(UTC)
    participant.is_email_verified = True
    participant.otp = None
    participant.is_sandbox_approved = True
    participant.is_approved = int(ApprovalStatus.APPROVED)
    participant.is_activated = int(ActivationStatus.ACTIVATED)
    participant.approved_date = now
    participant.activated_date = now
    db.commit()

    send_templated(
        db,
        TemplateCode.PARTICIPANT_WELCOME,
        participant.email_id,
        {"name": participant.display_name},
    )
    audit_service.record(
        db,
        Action.PARTICIPANT_VERIFY_EMAIL,
        actor_type="participant",
        actor_id=participant.participant_id,
        actor_name=participant.display_name,
        entity="participant",
        entity_id=participant.participant_id,
        country_code=participant.country_code,
    )
    return {"unique_id": participant.unique_id, "already_verified": False}


def resend_otp(db: Session, unique_id: str) -> dict:
    participant = _require_participant(db, unique_id)
    if participant.is_email_verified:
        raise ValidationError("This email address is already verified.")

    if participant.otp_request_count >= settings.OTP_MAX_REQUESTS_PER_HOUR and not (
        _otp_window_elapsed(participant.otp_generated_at)
    ):
        raise ValidationError(
            "Too many verification codes requested. Please try again later."
        )

    participant.otp = generate_otp()
    participant.otp_generated_at = datetime.now(UTC)
    participant.otp_request_count += 1
    db.commit()

    send_otp(db, participant.otp, email=participant.email_id)
    return {
        "masked_email": mask_email(participant.email_id),
        "otp_validity_seconds": settings.OTP_TTL_SECONDS,
        # True while mail is off: the code is DEV_FIXED_OTP, not an emailed one.
        "is_fixed_otp": bool(settings.fixed_otp),
    }


def is_email_available(db: Session, email_id: str) -> bool:
    return not ParticipantRepository(db).email_taken(email_id)


def get_registration_state(db: Session, unique_id: str) -> dict:
    """Let an interrupted signup pick up at the verification step."""
    participant = _require_participant(db, unique_id)
    return {
        "unique_id": participant.unique_id,
        "first_name": participant.first_name,
        "email_id": participant.email_id,
        "masked_email": mask_email(participant.email_id),
        "country_code": participant.country_code,
        "is_email_verified": participant.is_email_verified,
    }


def login(
    db: Session, email_id: str, password: str, user_agent: str | None = None
) -> ParticipantLoginResponse:
    participants = ParticipantRepository(db)
    participant = participants.get_by_email(email_id)

    if participant is None or not verify_password(password, participant.user_pass):
        raise UnauthorizedError(INVALID_CREDENTIALS)

    _assert_can_sign_in(participant)

    token = ParticipantTokenRepository(db).create(
        participant_id=participant.participant_id,
        ip_address=client_ip_ctx.get() or None,
        user_agent=user_agent,
    )

    audit_service.record(
        db,
        Action.PARTICIPANT_LOGIN,
        actor_type="participant",
        actor_id=participant.participant_id,
        actor_name=participant.display_name,
        country_code=participant.country_code,
        user_agent=user_agent,
    )

    return ParticipantLoginResponse(
        participant_id=participant.participant_id,
        unique_id=participant.unique_id,
        display_name=participant.display_name,
        first_name=participant.first_name,
        last_name=participant.last_name,
        company_name=participant.company_name,
        email_id=participant.email_id,
        country_code=participant.country_code,
        environments=available_environments(participant),
        is_profile_complete=participant.is_profile_complete,
        is_uat_requested=participant.is_uat_requested,
        is_prod_requested=participant.is_prod_requested,
        access_token=create_access_token(
            participant.participant_id, {"role": "participant"}
        ),
        refresh_token=create_refresh_token(
            participant.participant_id, {"role": "participant"}
        ),
        token_expiry=settings.JWT_ACCESS_TOKEN_EXPIRES,
        token_issued_at=datetime.now(UTC),
        auth_key=token.unique_id,
    )


def refresh_session(db: Session, refresh_token: str, auth_key: str | None) -> dict:
    """Issue a new access token for the session the refresh token belongs to."""
    claims = decode_token(refresh_token, refresh=True)
    if claims.get("typ") != "refresh" or claims.get("role") != "participant":
        raise UnauthorizedError("Unauthorized! Invalid refresh token.")
    if not auth_key:
        raise UnauthorizedError("Session is expired or invalid.")

    tokens = ParticipantTokenRepository(db)
    token = tokens.get_active(auth_key)
    if token is None or str(token.participant_id) != str(claims.get("id")):
        raise UnauthorizedError("Session is expired or invalid.")

    participant = ParticipantRepository(db).get(token.participant_id)
    if participant is None or participant.is_deleted:
        raise UnauthorizedError("Your account no longer exists.")
    if not participant.is_enabled:
        raise ForbiddenError(
            "Your account has been blocked, contact the system administrator."
        )
    tokens.touch(token)

    return {
        "access_token": create_access_token(
            participant.participant_id, {"role": "participant"}
        ),
        "token_expiry": settings.JWT_ACCESS_TOKEN_EXPIRES,
        "token_issued_at": datetime.now(UTC),
    }


def logout(db: Session, auth_key: str, participant_id: int) -> None:
    tokens = ParticipantTokenRepository(db)
    token = tokens.get_active(auth_key)
    if token is not None:
        tokens.logout(token)
    audit_service.record(
        db,
        Action.PARTICIPANT_LOGOUT,
        actor_type="participant",
        actor_id=participant_id,
    )


def change_password(
    db: Session, participant: Participant, old_password: str, new_password: str
) -> None:
    if not verify_password(old_password, participant.user_pass):
        raise ValidationError("Current password is incorrect.")
    if verify_password(new_password, participant.user_pass):
        raise ValidationError(
            "New password must be different from the current password."
        )

    participant.user_pass = hash_password(new_password)
    db.commit()


def request_password_reset(db: Session, email_id: str) -> None:
    participant = ParticipantRepository(db).get_by_email(email_id)
    if participant is None:
        # Silent no-op: the caller always reports the same message, so this
        # endpoint cannot be used to enumerate registered addresses.
        return

    participant.reset_pass_token = generate_token_urlsafe()
    participant.reset_pass_token_time = datetime.now(UTC)
    db.commit()

    send_templated(
        db,
        TemplateCode.PARTICIPANT_RESET_PASSWORD,
        participant.email_id,
        {"name": participant.display_name, "token": participant.reset_pass_token},
    )


def reset_password(db: Session, token: str, new_password: str) -> None:
    participants = ParticipantRepository(db)
    participant = participants.get_by_reset_token(token)
    if participant is None:
        raise NotFoundError("This link is not valid.")
    if _reset_token_expired(participant.reset_pass_token_time):
        raise ValidationError("This link has expired, please request a new one.")

    participant.user_pass = hash_password(new_password)
    participant.reset_pass_token = None
    participant.reset_pass_token_time = None
    db.commit()


def reset_password_with_code(
    db: Session, email_id: str, otp: str, new_password: str
) -> None:
    """Development reset while no mail is sent: email + DEV_FIXED_OTP.

    Only after "forgot password" was requested for the account and within the
    same expiry as the emailed link; refused whenever real mail is on.
    """
    if not settings.fixed_otp:
        raise ValidationError("Use the reset link sent to your email.")
    participant = ParticipantRepository(db).get_by_email(email_id)
    if (
        participant is None
        or not participant.reset_pass_token
        or otp != settings.fixed_otp
    ):
        raise ValidationError("The code is not valid. Request a new one.")
    if _reset_token_expired(participant.reset_pass_token_time):
        raise ValidationError("The code has expired, please request a new one.")
    reset_password(db, participant.reset_pass_token, new_password)


def available_environments(participant: Participant) -> list[str]:
    environments = []
    if participant.is_sandbox_approved:
        environments.append(str(Environment.SANDBOX))
    if participant.is_uat_approved:
        environments.append(str(Environment.UAT))
    if participant.is_prod_approved and participant.is_prod_enabled:
        environments.append(str(Environment.PRODUCTION))
    return environments


# ------------------------------------------------------------------ helpers
def _require_participant(db: Session, unique_id: str) -> Participant:
    participant = ParticipantRepository(db).get_by(unique_id=unique_id)
    if participant is None:
        raise NotFoundError("Registration not found.")
    return participant


def _assert_can_sign_in(participant: Participant) -> None:
    if not participant.is_email_verified:
        raise UnauthorizedError("Please verify your email address before signing in.")
    if participant.is_rejected:
        raise UnauthorizedError(
            participant.rejection_reason or "Your account is not approved."
        )
    if not participant.is_enabled or participant.is_activated == int(
        ActivationStatus.BLOCKED
    ):
        raise UnauthorizedError(
            "Your account has been blocked, contact the administrator."
        )


def _otp_expired(generated_at: datetime | None) -> bool:
    if generated_at is None:
        return True
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - generated_at > timedelta(
        seconds=settings.OTP_TTL_SECONDS
    )


def _otp_window_elapsed(generated_at: datetime | None) -> bool:
    """True once the rate-limit window since the last code has passed."""
    if generated_at is None:
        return True
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - generated_at > timedelta(hours=1)


def _reset_token_expired(issued_at: datetime | None) -> bool:
    if issued_at is None:
        return True
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - issued_at > timedelta(hours=RESET_TOKEN_TTL_HOURS)
