"""Portal registration and authentication.

Registration is deliberately short: one form, then an emailed code. Verifying
the code files the UAT request; an administrator reviews the sign-up details
and approving UAT opens the account (no sign-in before that). Organisation
details are collected later, and reviewed when the participant asks for
production access.

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
    UpstreamError,
    ValidationError,
)
from app.core.security import (
    codes_match,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    generate_token_urlsafe,
    hash_password,
    session_expired,
    sha256_token,
    verify_password,
    verify_password_or_dummy,
)
from app.integrations import keycloak_oidc
from app.models.enums import ActivationStatus, ApprovalStatus, Environment
from app.models.participant import Participant
from app.repositories.participant_repository import (
    ParticipantRepository,
    ParticipantRequestRepository,
    ParticipantTokenRepository,
)
from app.schemas.participant import ParticipantLoginResponse, SignupRequest
from app.services import audit_service, auth_throttle_service, iam_user_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_otp, send_templated
from app.utils.common import mask_email

INVALID_CREDENTIALS = "No such email address or password."
RESET_TOKEN_TTL_HOURS = 2


def signup(db: Session, payload: SignupRequest) -> dict:
    """Create the account and email the verification code.

    The row is written unverified. Nothing but the verification step is
    possible until the code is entered; the verified sign-up then waits for an
    administrator to approve or reject UAT (``/admin/participants/pending``).
    Nothing is created in Keycloak until that approval.

    While mail cannot be sent there is no code to enter: the address is taken
    as verified and the UAT request is filed at once.
    """
    auth_throttle_service.limit_ip(db, "signup")
    participants = ParticipantRepository(db)
    if participants.email_taken(payload.email_id):
        raise ConflictError("An account with this email address already exists.")

    if not settings.mail_active:
        return _signup_for_approval(db, participants, payload)

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
        "requires_verification": True,
        "pending_approval": False,
    }


def _signup_for_approval(
    db: Session, participants: ParticipantRepository, payload: SignupRequest
) -> dict:
    """Mail is off: register without a code, pending administrator approval."""
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
        is_email_verified=True,
        is_approved=int(ApprovalStatus.PENDING),
        ip_address=client_ip_ctx.get() or None,
    )
    _file_uat_request(db, participant)
    audit_service.record(
        db,
        Action.PARTICIPANT_SIGNUP,
        actor_type="participant",
        actor_name=participant.display_name,
        entity="participant",
        entity_id=participant.participant_id,
        description="Registered without email verification (mail is off); awaiting UAT approval",
        country_code=participant.country_code,
    )
    return {
        "unique_id": participant.unique_id,
        "masked_email": mask_email(participant.email_id),
        "otp_validity_seconds": 0,
        "is_fixed_otp": False,
        "requires_verification": False,
        "pending_approval": True,
    }


def verify_email(db: Session, unique_id: str, otp: str) -> dict:
    """Confirm the emailed code and file the UAT request.

    The account stays closed (no sign-in) until an administrator approves UAT.
    """
    auth_throttle_service.limit_ip(db, "verify-email")
    participant = _require_participant(db, unique_id)

    if participant.is_email_verified:
        return {"unique_id": participant.unique_id, "already_verified": True}
    throttle_key = f"otp:{participant.unique_id}"
    auth_throttle_service.assert_not_locked(db, throttle_key)
    if not codes_match(otp, participant.otp):
        failures = auth_throttle_service.record_failure(
            db, throttle_key, settings.OTP_MAX_ATTEMPTS
        )
        if failures >= settings.OTP_MAX_ATTEMPTS:
            # Too many guesses: this code is dead, a new one must be requested.
            participant.otp = None
            db.commit()
        raise ValidationError("The verification code is incorrect.")
    auth_throttle_service.clear(db, throttle_key)
    if _otp_expired(participant.otp_generated_at):
        raise ValidationError(
            "The verification code has expired, please request a new one."
        )

    participant.is_email_verified = True
    participant.otp = None
    db.commit()
    _file_uat_request(db, participant)

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
    return {
        "unique_id": participant.unique_id,
        "already_verified": False,
        "pending_approval": True,
    }


def resend_otp(db: Session, unique_id: str) -> dict:
    auth_throttle_service.limit_ip(db, "resend-otp")
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
    auth_throttle_service.limit_ip(db, "check-email")
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
    auth_throttle_service.limit_ip(db, "participant-login")
    throttle_key = f"login:participant:{(email_id or '').strip().lower()}"
    auth_throttle_service.assert_not_locked(db, throttle_key)

    participants = ParticipantRepository(db)
    participant = participants.get_by_email(email_id)

    kc_tokens = None
    if settings.keycloak_login and participant is not None and _may_sign_in(participant):
        # Keycloak checks the password and issues the tokens.
        kc_tokens = _keycloak_sign_in(db, participant, password, throttle_key)
    else:
        # The sandbox's own check. With Keycloak sign-in it is used only for a
        # participant who may not sign in (not approved yet, rejected, blocked):
        # it picks the message, never opens a session.
        if not verify_password_or_dummy(password, participant.user_pass if participant else None):
            auth_throttle_service.record_failure(db, throttle_key)
            raise UnauthorizedError(INVALID_CREDENTIALS)
        auth_throttle_service.clear(db, throttle_key)
        _assert_can_sign_in(participant)
        iam_user_service.signed_in(db, participant, password)

    token = ParticipantTokenRepository(db).create(
        participant_id=participant.participant_id,
        ip_address=client_ip_ctx.get() or None,
        user_agent=user_agent,
        keycloak_sid=kc_tokens.claims["sid"] if kc_tokens else None,
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
        access_token=kc_tokens.access_token if kc_tokens else create_access_token(
            participant.participant_id, {"role": "participant"}
        ),
        refresh_token=kc_tokens.refresh_token if kc_tokens else create_refresh_token(
            participant.participant_id, {"role": "participant"}
        ),
        token_expiry=kc_tokens.expires_in if kc_tokens else settings.JWT_ACCESS_TOKEN_EXPIRES,
        token_issued_at=datetime.now(UTC),
        auth_key=token.unique_id,
    )


def _may_sign_in(participant: Participant) -> bool:
    try:
        _assert_can_sign_in(participant)
    except UnauthorizedError:
        return False
    return True


def _keycloak_sign_in(
    db: Session, participant: Participant, password: str, throttle_key: str
) -> keycloak_oidc.Tokens:
    """Keycloak's direct grant for an approved participant.

    Transition: a participant approved before Keycloak held its password (the
    sandbox only had a hash) is let in once more by the sandbox's own check,
    which hands Keycloak the password; Keycloak checks every sign-in after that.
    """
    username = participant.email_id.lower()
    try:
        tokens = keycloak_oidc.password_grant(username, password)
    except keycloak_oidc.InvalidCredentials:
        if not (iam_user_service.needs_password(db, participant)
                and verify_password(password, participant.user_pass)):
            auth_throttle_service.record_failure(db, throttle_key)
            raise UnauthorizedError(INVALID_CREDENTIALS) from None
        iam_user_service.signed_in(db, participant, password)
        try:
            tokens = keycloak_oidc.password_grant(username, password)
        except keycloak_oidc.InvalidCredentials:
            raise UpstreamError(
                "Your sign-in could not be set up, please try again shortly or contact the administrator."
            ) from None
    auth_throttle_service.clear(db, throttle_key)
    if tokens.claims.get("participant_uid") != str(participant.unique_id):
        # A Keycloak user with this email that the sandbox did not make.
        keycloak_oidc.end_session(tokens.claims.get("sid"))
        raise UnauthorizedError(INVALID_CREDENTIALS)
    return tokens


def refresh_session(db: Session, refresh_token: str, auth_key: str | None) -> dict:
    """Issue a new access token for the session the refresh token belongs to."""
    if settings.keycloak_login:
        return _keycloak_refresh(db, refresh_token, auth_key)
    claims = decode_token(refresh_token, refresh=True, role="participant")
    if not auth_key:
        raise UnauthorizedError("Session is expired or invalid.")

    tokens = ParticipantTokenRepository(db)
    token = tokens.get_active(auth_key)
    if token is None or str(token.participant_id) != str(claims.get("id")):
        raise UnauthorizedError("Session is expired or invalid.")
    if session_expired(token.added_date, token.last_action):
        tokens.logout(token)
        raise UnauthorizedError("Session has expired, please sign in again.")

    participant = ParticipantRepository(db).get(token.participant_id)
    if participant is None or participant.is_deleted:
        raise UnauthorizedError("Your account no longer exists.")
    if not participant.is_enabled:
        raise ForbiddenError(
            "Your account has been blocked, contact the system administrator."
        )
    # A session started before a rejection or block ends here too.
    _assert_can_sign_in(participant)
    tokens.touch(token)

    return {
        "access_token": create_access_token(
            participant.participant_id, {"role": "participant"}
        ),
        "token_expiry": settings.JWT_ACCESS_TOKEN_EXPIRES,
        "token_issued_at": datetime.now(UTC),
    }


def _keycloak_refresh(db: Session, refresh_token: str, auth_key: str | None) -> dict:
    """Keycloak's refresh grant, for a live sandbox session of the same Keycloak session."""
    tokens = ParticipantTokenRepository(db)
    token = tokens.get_active(auth_key) if auth_key else None
    if token is None or not token.keycloak_sid:
        raise UnauthorizedError("Session is expired or invalid.")
    if session_expired(token.added_date, token.last_action):
        tokens.logout(token)
        keycloak_oidc.end_session(token.keycloak_sid)
        raise UnauthorizedError("Session has expired, please sign in again.")
    fresh = keycloak_oidc.refresh_grant(refresh_token)
    participant = ParticipantRepository(db).get(token.participant_id)
    if (
        fresh.claims.get("sid") != token.keycloak_sid
        or participant is None
        or fresh.claims.get("participant_uid") != str(participant.unique_id)
    ):
        raise UnauthorizedError("Session is expired or invalid.")
    if participant.is_deleted:
        raise UnauthorizedError("Your account no longer exists.")
    if not participant.is_enabled:
        raise ForbiddenError("Your account has been blocked, contact the system administrator.")
    _assert_can_sign_in(participant)
    tokens.touch(token)
    return {
        "access_token": fresh.access_token,
        # Keycloak may rotate the refresh token: the portal keeps the new one.
        "refresh_token": fresh.refresh_token or refresh_token,
        "token_expiry": fresh.expires_in,
        "token_issued_at": datetime.now(UTC),
    }


def logout(db: Session, auth_key: str, participant_id: int) -> None:
    tokens = ParticipantTokenRepository(db)
    token = tokens.get_active(auth_key)
    if token is not None:
        tokens.logout(token)
        keycloak_oidc.end_session(token.keycloak_sid)
    audit_service.record(
        db,
        Action.PARTICIPANT_LOGOUT,
        actor_type="participant",
        actor_id=participant_id,
    )


def change_password(
    db: Session,
    participant: Participant,
    old_password: str,
    new_password: str,
    current_auth_key: str | None = None,
) -> None:
    if settings.keycloak_login and not iam_user_service.needs_password(db, participant):
        # Keycloak holds the password, so it checks the current one.
        try:
            check = keycloak_oidc.password_grant(participant.email_id.lower(), old_password)
        except keycloak_oidc.InvalidCredentials:
            raise ValidationError("Current password is incorrect.") from None
        keycloak_oidc.revoke_refresh_token(check.refresh_token)
        if old_password == new_password:
            raise ValidationError("New password must be different from the current password.")
    else:
        if not verify_password(old_password, participant.user_pass):
            raise ValidationError("Current password is incorrect.")
        if verify_password(new_password, participant.user_pass):
            raise ValidationError(
                "New password must be different from the current password."
            )

    participant.user_pass = hash_password(new_password)
    db.commit()
    # Other devices sign in again with the new password; this one stays.
    ParticipantTokenRepository(db).logout_all(participant.participant_id, keep=current_auth_key)
    iam_user_service.password_changed(db, participant, new_password)


def request_password_reset(db: Session, email_id: str) -> None:
    auth_throttle_service.limit_ip(db, "participant-forgot")
    participant = ParticipantRepository(db).get_by_email(email_id)
    if participant is None:
        # Silent no-op: the caller always reports the same message, so this
        # endpoint cannot be used to enumerate registered addresses.
        return

    token = generate_token_urlsafe()
    # Only the hash is stored; the link in the mail carries the token itself.
    participant.reset_pass_token = sha256_token(token)
    participant.reset_pass_token_time = datetime.now(UTC)
    db.commit()

    send_templated(
        db,
        TemplateCode.PARTICIPANT_RESET_PASSWORD,
        participant.email_id,
        {"name": participant.display_name, "token": token},
    )


def reset_password(db: Session, token: str, new_password: str) -> None:
    auth_throttle_service.limit_ip(db, "participant-reset")
    participants = ParticipantRepository(db)
    participant = participants.get_by_reset_token(token)
    if participant is None:
        raise NotFoundError("This link is not valid.")
    if _reset_token_expired(participant.reset_pass_token_time):
        raise ValidationError("This link has expired, please request a new one.")

    _set_new_password(db, participant, new_password)


def _set_new_password(db: Session, participant: Participant, new_password: str) -> None:
    participant.user_pass = hash_password(new_password)
    participant.reset_pass_token = None
    participant.reset_pass_token_time = None
    db.commit()
    # Whoever held a session before the reset is signed out.
    ParticipantTokenRepository(db).logout_all(participant.participant_id)
    iam_user_service.password_changed(db, participant, new_password)


def reset_password_with_code(
    db: Session, email_id: str, otp: str, new_password: str
) -> None:
    """Developer-machine reset while no mail is sent: email + DEV_FIXED_OTP.

    Only with ENV=local (see ``settings.fixed_otp``), only after "forgot
    password" was requested for the account, and within the same expiry as the
    emailed link.
    """
    if not settings.fixed_otp:
        raise ValidationError("Use the reset link sent to your email.")
    auth_throttle_service.limit_ip(db, "participant-reset")
    participant = ParticipantRepository(db).get_by_email(email_id)
    if (
        participant is None
        or not participant.reset_pass_token
        or not codes_match(otp, settings.fixed_otp)
    ):
        raise ValidationError("The code is not valid. Request a new one.")
    if _reset_token_expired(participant.reset_pass_token_time):
        raise ValidationError("The code has expired, please request a new one.")
    _set_new_password(db, participant, new_password)


def available_environments(participant: Participant) -> list[str]:
    environments = []
    if participant.is_uat_approved:
        environments.append(str(Environment.UAT))
    if participant.is_prod_approved and participant.is_prod_enabled:
        environments.append(str(Environment.PRODUCTION))
    return environments


# ------------------------------------------------------------------ helpers
def _file_uat_request(db: Session, participant: Participant) -> None:
    """The sign-up is the UAT request: list it in UAT approval pending."""
    requests = ParticipantRequestRepository(db)
    if not requests.has_open_request(participant.participant_id, Environment.UAT):
        requests.create(
            participant_id=participant.participant_id,
            target_environment=str(Environment.UAT),
            status=int(ApprovalStatus.PENDING),
            remarks="Sign-up",
            added_by=participant.participant_id,
        )
    participant.is_uat_requested = True
    participant.is_uat_rejected = False
    db.commit()


def _require_participant(db: Session, unique_id: str) -> Participant:
    participant = ParticipantRepository(db).get_by(unique_id=unique_id)
    if participant is None:
        raise NotFoundError("Registration not found.")
    return participant


def _assert_can_sign_in(participant: Participant) -> None:
    if participant.is_rejected:
        raise UnauthorizedError(
            participant.rejection_reason or "Your account is not approved."
        )
    if not participant.is_email_verified and settings.mail_active:
        raise UnauthorizedError("Please verify your email address before signing in.")
    if participant.is_approved == int(ApprovalStatus.PENDING):
        raise UnauthorizedError(
            "Your registration is waiting for UAT approval by an administrator."
            " You will receive an email once it is approved."
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
