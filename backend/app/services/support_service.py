"""Support tickets as conversations.

A ticket (``ParticipantQuery``) holds messages (``ParticipantQueryMessage``), oldest
first. Participants and administrators each add messages; administrators can also
keep staff-only notes that never reach the participant.

Status: 0 open, 1 in progress, 2 answered (waiting for the participant), 3 closed.
An answer sets 2, a participant's reply puts an answered ticket back to 0, a closed
ticket takes no more replies. The SLA clock (``awaiting_since``) runs from the
participant's last message until an administrator answers.

Mail is sent through ``notification_service`` with threading headers (``Message-ID``,
``In-Reply-To``, ``References``) and the ticket number in the subject, and the id is
kept in ``external_id``: replies that come back by mail can be matched to their
ticket later without changing the model.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.deps import AdminPrincipal, ParticipantPrincipal
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.participant import (
    Participant,
    ParticipantQuery,
    ParticipantQueryMessage,
)
from app.repositories.participant_repository import (
    ParticipantQueryMessageRepository,
    ParticipantQueryRepository,
    ParticipantRepository,
)
from app.schemas.participant import (
    AdminQueryOut,
    AdminQueryThreadOut,
    QueryListQuery,
    QueryMessageOut,
    QueryOut,
    QueryThreadOut,
    ticket_number,
)
from app.services import audit_service
from app.services.audit_service import Action
from app.services.notification_service import TemplateCode, send_templated

logger = get_logger(__name__)

OPEN, IN_PROGRESS, ANSWERED, CLOSED = 0, 1, 2, 3
STATUS_LABELS = {OPEN: "Open", IN_PROGRESS: "In progress", ANSWERED: "Answered", CLOSED: "Closed"}

PARTICIPANT, ADMIN, SYSTEM = "participant", "admin", "system"


# ----------------------------------------------------------------- helpers
def _now() -> datetime:
    return datetime.now(UTC)


def _aware(moment: datetime | None) -> datetime | None:
    return None if moment is None else (moment if moment.tzinfo else moment.replace(tzinfo=UTC))


def _ticket(db: Session, query_id: int) -> ParticipantQuery:
    query = ParticipantQueryRepository(db).get(query_id)
    if query is None:
        raise NotFoundError("Ticket not found.")
    return query


def _own_ticket(db: Session, participant: Participant, query_id: int) -> ParticipantQuery:
    query = _ticket(db, query_id)
    # Someone else's ticket is "not found", not "forbidden".
    if query.participant_id != participant.participant_id:
        raise NotFoundError("Ticket not found.")
    return query


def _ticket_url() -> str:
    return f"{settings.portal_base_url}/participant/support"


def _mail_domain() -> str:
    sender = settings.SMTP_FROM or ""
    return sender.rsplit("@", 1)[-1].strip(">").strip() or "oan.local"


def _mail_headers(db: Session, query: ParticipantQuery, message_id: str) -> dict[str, str]:
    """Threading headers: replies group under the ticket in the participant's mail client."""
    headers = {"Message-ID": message_id, "X-OAN-Ticket": ticket_number(query.query_id)}
    previous = ParticipantQueryMessageRepository(db).last_external_id(query.query_id)
    if previous:
        headers["In-Reply-To"] = previous
        headers["References"] = previous
    return headers


def _add_message(
    db: Session,
    query: ParticipantQuery,
    author_type: str,
    body: str,
    *,
    author_id: int | None = None,
    author_name: str | None = None,
    internal: bool = False,
    channel: str = "portal",
    external_id: str | None = None,
) -> ParticipantQueryMessage:
    """Append a message and keep the ticket's summary fields in step (caller commits)."""
    repo = ParticipantQueryMessageRepository(db)
    if author_type != SYSTEM and repo.count_for(query.query_id) >= settings.SUPPORT_MAX_MESSAGES_PER_TICKET:
        raise ConflictError(
            f"This ticket has reached {settings.SUPPORT_MAX_MESSAGES_PER_TICKET} messages. "
            "Please raise a new ticket for anything further."
        )
    now = _now()
    message = repo.create(
        commit=False,
        query_id=query.query_id,
        author_type=author_type,
        author_id=author_id,
        author_name=author_name,
        body=body,
        is_internal=internal,
        channel=channel,
        external_id=external_id,
        added_date=now,
        modify_date=now,
    )
    if author_type != SYSTEM and not internal:
        query.last_message_date = now
        query.last_message_by = author_type
    return message


def _set_status(query: ParticipantQuery, status: int) -> None:
    query.status = status
    if status == CLOSED:
        query.closed_date = _now()
        query.awaiting_since = None
    else:
        query.closed_date = None
        if status == ANSWERED:
            query.awaiting_since = None


def _author_name(participant: Participant) -> str:
    return participant.display_name or participant.full_name or participant.email_id or "Participant"


def _admin_name(admin: AdminPrincipal) -> str:
    return admin.user.full_name or admin.user.login_name or "Support"


# ------------------------------------------------------------------ views
def _unread(query: ParticipantQuery, viewer: str) -> bool:
    """The other side wrote after the viewer last opened the ticket."""
    other = ADMIN if viewer == PARTICIPANT else PARTICIPANT
    if query.last_message_by != other:
        return False
    seen = _aware(query.participant_read_date if viewer == PARTICIPANT else query.admin_read_date)
    wrote = _aware(query.last_message_date)
    return wrote is not None and (seen is None or wrote > seen)


def _messages(db: Session, query_id: int, internal: bool) -> list[QueryMessageOut]:
    rows = ParticipantQueryMessageRepository(db).thread(query_id, include_internal=internal)
    return [QueryMessageOut.model_validate(row) for row in rows]


def _participant_view(row: ParticipantQuery, counts: dict[int, int]) -> QueryOut:
    return QueryOut.model_validate(row).model_copy(
        update={"message_count": counts.get(row.query_id, 0), "unread": _unread(row, PARTICIPANT)}
    )


def list_for_participant(db: Session, participant_id: int) -> list[QueryOut]:
    rows = ParticipantQueryRepository(db).list_all(participant_id=participant_id)
    counts = ParticipantQueryMessageRepository(db).counts([r.query_id for r in rows], include_internal=False)
    return [_participant_view(row, counts) for row in rows]


def participant_thread(db: Session, participant: Participant, query_id: int) -> QueryThreadOut:
    """The conversation as the participant sees it (no staff notes); opening it marks it read."""
    query = _own_ticket(db, participant, query_id)
    query.participant_read_date = _now()
    db.commit()
    counts = ParticipantQueryMessageRepository(db).counts([query_id], include_internal=False)
    view = _participant_view(query, counts)
    return QueryThreadOut(**view.model_dump(exclude={"ticket_no", "due_date", "is_overdue"}),
                          messages=_messages(db, query_id, internal=False))


def _admin_row(query: ParticipantQuery, participant: Participant | None, counts: dict[int, int]) -> AdminQueryOut:
    return AdminQueryOut.model_validate(query).model_copy(
        update={
            "participant_name": participant.full_name if participant else None,
            "email_id": participant.email_id if participant else None,
            "company_name": participant.company_name if participant else None,
            "message_count": counts.get(query.query_id, 0),
            "unread": _unread(query, ADMIN),
        }
    )


def list_queries(db: Session, query: QueryListQuery):
    """Console list of tickets, each with the participant who raised it."""
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
    counts = ParticipantQueryMessageRepository(db).counts([r.query_id for r in page.rows], include_internal=True)
    page.rows = [_admin_row(row, participants.get(row.participant_id), counts) for row in page.rows]
    return page


def admin_thread(db: Session, admin: AdminPrincipal, query_id: int) -> AdminQueryThreadOut:
    """The whole conversation including staff notes; opening it marks it read."""
    query = _ticket(db, query_id)
    query.admin_read_date = _now()
    db.commit()
    participant = ParticipantRepository(db).get(query.participant_id) if query.participant_id else None
    counts = ParticipantQueryMessageRepository(db).counts([query_id], include_internal=True)
    row = _admin_row(query, participant, counts)
    return AdminQueryThreadOut(**row.model_dump(exclude={"ticket_no", "due_date", "is_overdue"}),
                               messages=_messages(db, query_id, internal=True))


# ---------------------------------------------------------------- participant
def create_ticket(
    db: Session, principal: ParticipantPrincipal, subject: str, description: str, query_type: int | None
) -> QueryOut:
    participant = principal.participant
    now = _now()
    query = ParticipantQueryRepository(db).create(
        commit=False,
        participant_id=participant.participant_id,
        query_type=query_type,
        subject=subject,
        description=description,
        added_by=participant.participant_id,
        last_message_date=now,
        last_message_by=PARTICIPANT,
        participant_read_date=now,
    )
    _add_message(
        db, query, PARTICIPANT, description,
        author_id=participant.participant_id, author_name=_author_name(participant),
    )
    db.commit()
    audit_service.record_participant(
        db, principal, Action.SUPPORT_TICKET_CREATE, entity="support_ticket", entity_id=query.query_id,
        description=f"Raised ticket {ticket_number(query.query_id)}",
    )
    _tell_support(db, query, participant, description)
    return _participant_view(query, {query.query_id: 1})


def participant_reply(db: Session, principal: ParticipantPrincipal, query_id: int, body: str) -> QueryThreadOut:
    participant = principal.participant
    query = _own_ticket(db, participant, query_id)
    if query.status == CLOSED:
        raise ConflictError("This ticket is closed. Please raise a new ticket.")
    _add_message(
        db, query, PARTICIPANT, body,
        author_id=participant.participant_id, author_name=_author_name(participant),
    )
    if query.status == ANSWERED:
        # They answered back: the team owes the next reply, so the SLA clock restarts.
        query.status = OPEN
        query.awaiting_since = _now()
    query.participant_read_date = _now()
    db.commit()
    audit_service.record_participant(
        db, principal, Action.SUPPORT_REPLY, entity="support_ticket", entity_id=query.query_id,
        description=f"Wrote on ticket {ticket_number(query.query_id)}",
    )
    _tell_support(db, query, participant, body)
    return participant_thread(db, participant, query_id)


def participant_close(db: Session, principal: ParticipantPrincipal, query_id: int) -> QueryThreadOut:
    """The participant marks their ticket resolved."""
    participant = principal.participant
    query = _own_ticket(db, participant, query_id)
    if query.status != CLOSED:
        _set_status(query, CLOSED)
        _add_message(db, query, SYSTEM, "The participant closed this ticket.", author_name=_author_name(participant))
        db.commit()
        audit_service.record_participant(
            db, principal, Action.SUPPORT_STATUS, entity="support_ticket", entity_id=query.query_id,
            description=f"Closed ticket {ticket_number(query.query_id)}",
        )
    return participant_thread(db, participant, query_id)


# ---------------------------------------------------------------------- admin
def admin_message(
    db: Session,
    admin: AdminPrincipal,
    query_id: int,
    body: str,
    *,
    internal: bool = False,
    status: int | None = None,
) -> AdminQueryThreadOut:
    """A reply to the participant (emailed) or, with ``internal``, a staff-only note."""
    query = _ticket(db, query_id)
    name = _admin_name(admin)
    if internal:
        _add_message(db, query, ADMIN, body, author_id=admin.id, author_name=name, internal=True)
        db.commit()
        audit_service.record_admin(
            db, admin, Action.SUPPORT_NOTE, entity="support_ticket", entity_id=query_id,
            description=f"Noted ticket {ticket_number(query_id)}",
        )
        return admin_thread(db, admin, query_id)

    new_status = ANSWERED if status is None else status
    message = _add_message(db, query, ADMIN, body, author_id=admin.id, author_name=name)
    _set_status(query, new_status)
    query.response = body
    query.responded_by = admin.id
    query.responded_date = _now()
    query.admin_read_date = _now()
    db.commit()
    audit_service.record_admin(
        db, admin, Action.SUPPORT_REPLY, entity="support_ticket", entity_id=query_id,
        description=f"Replied on ticket {ticket_number(query_id)}",
    )
    _email_participant(db, query, message)
    return admin_thread(db, admin, query_id)


def admin_set_status(db: Session, admin: AdminPrincipal, query_id: int, status: int) -> AdminQueryThreadOut:
    query = _ticket(db, query_id)
    if query.status != status:
        _set_status(query, status)
        _add_message(db, query, SYSTEM, f"Status changed to {STATUS_LABELS[status]}.", author_name=_admin_name(admin))
        db.commit()
        audit_service.record_admin(
            db, admin, Action.SUPPORT_STATUS, entity="support_ticket", entity_id=query_id,
            description=f"Ticket {ticket_number(query_id)} set to {STATUS_LABELS[status]}",
        )
    return admin_thread(db, admin, query_id)


def respond_to_query(db: Session, admin: AdminPrincipal, query_id: int, response: str, status: int) -> ParticipantQuery:
    """The original one-shot reply API: now simply a message on the thread."""
    admin_message(db, admin, query_id, response, status=status)
    return _ticket(db, query_id)


def close_stale_tickets(db: Session) -> int:
    """Close answered tickets the participant has not touched for SUPPORT_AUTO_CLOSE_DAYS."""
    days = settings.SUPPORT_AUTO_CLOSE_DAYS
    if days <= 0:
        return 0
    cutoff = _now() - timedelta(days=days)
    stale = db.execute(
        select(ParticipantQuery).where(
            ParticipantQuery.status == ANSWERED, ParticipantQuery.last_message_date < cutoff
        )
    ).scalars().all()
    for query in stale:
        _set_status(query, CLOSED)
        _add_message(db, query, SYSTEM, f"Closed automatically after {days} days without a reply.")
    if stale:
        db.commit()
    return len(stale)


# --------------------------------------------------------------------- email
def _email_participant(db: Session, query: ParticipantQuery, message: ParticipantQueryMessage) -> None:
    """Mail an administrator's reply to the participant (best effort: the reply is saved either way)."""
    participant = ParticipantRepository(db).get(query.participant_id) if query.participant_id else None
    if participant is None or not participant.email_id:
        return
    message_id = f"<{ticket_number(query.query_id).lower()}.{uuid.uuid4().hex}@{_mail_domain()}>"
    try:
        sent = send_templated(
            db,
            TemplateCode.QUERY_RESPONSE,
            participant.email_id,
            {
                "name": participant.display_name,
                "subject": query.subject,
                "response": message.body,
                "ticket_no": ticket_number(query.query_id),
                "ticket_url": _ticket_url(),
            },
            headers=_mail_headers(db, query, message_id),
        )
    except Exception as exc:  # the reply is already saved; mail trouble must not undo it
        logger.error("Mail for ticket %s failed: %s", query.query_id, exc)
        return
    if sent:
        message.external_id = message_id
        message.notified_date = _now()
        db.commit()


def _tell_support(db: Session, query: ParticipantQuery, participant: Participant, body: str) -> None:
    """Tell the support mailbox (SUPPORT_NOTIFY_EMAIL) that a participant wrote; nothing if unset."""
    if not settings.SUPPORT_NOTIFY_EMAIL:
        return
    try:
        send_templated(
            db,
            TemplateCode.QUERY_NEW_MESSAGE,
            settings.SUPPORT_NOTIFY_EMAIL,
            {
                "participant_name": _author_name(participant),
                "subject": query.subject,
                "message": body,
                "ticket_no": ticket_number(query.query_id),
            },
        )
    except Exception as exc:
        logger.error("Support notice for ticket %s failed: %s", query.query_id, exc)
