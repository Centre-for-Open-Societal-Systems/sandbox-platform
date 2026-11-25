"""Support tickets as conversations: replies both ways, staff notes, status, unread, email seam."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.config.settings import settings
from app.models.participant import ParticipantQuery, ParticipantQueryMessage
from app.services import support_service
from tests.conftest import PARTICIPANT_PASSWORD
from tests.test_support_and_security import _login_participant, _second_participant

P = "/oan/participant/queries"
A = "/oan/admin/participants/queries"


@pytest.fixture
def mails(monkeypatch) -> list[dict]:
    """Mails the ticket service sends: ``{"code", "to", "values", "headers"}``."""
    sent: list[dict] = []

    def _capture(db, code, to, values, locale="en", headers=None):
        sent.append({"code": code, "to": to, "values": dict(values), "headers": dict(headers or {})})
        return True

    monkeypatch.setattr("app.services.support_service.send_templated", _capture)
    return sent


def _ticket(client, participant_headers, subject="Token problem", text="My token fails on every call."):
    response = client.post(
        P, headers=participant_headers, json={"query_type": 1, "subject": subject, "description": text}
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["query_id"]


def _admin_say(client, admin_headers, qid, body, **extra):
    response = client.post(f"{A}/{qid}/messages", headers=admin_headers, json={"body": body, **extra})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _say(client, participant_headers, qid, body):
    return client.post(f"{P}/{qid}/messages", headers=participant_headers, json={"body": body})


def _roles(thread) -> list[str]:
    return [m["author_type"] for m in thread["messages"]]


def test_a_ticket_is_a_conversation(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)

    answered = _admin_say(client, admin_headers, qid, "Please send the exact error.")
    assert answered["status"] == 2 and answered["ticket_no"] == f"TKT-{qid:06d}"

    back = _say(client, participant_headers, qid, "It says 401 invalid token.")
    assert back.status_code == 200, back.text
    thread = back.json()["data"]
    # They answered the team: the ticket is open again and the SLA clock restarted.
    assert thread["status"] == 0 and thread["awaiting_since"] is not None
    assert _roles(thread) == ["participant", "admin", "participant"]
    assert thread["messages"][1]["author_name"]

    _admin_say(client, admin_headers, qid, "Refresh the token and retry.")
    seen = client.get(f"{P}/{qid}", headers=participant_headers).json()["data"]
    assert [m["body"] for m in seen["messages"]][-1] == "Refresh the token and retry."
    assert seen["message_count"] == 4


def test_staff_notes_never_reach_the_participant(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)

    note = _admin_say(client, admin_headers, qid, "Looks like a duplicate of the Tuesday outage.", internal=True)

    assert note["status"] == 0  # a note changes nothing
    assert mails == []  # and sends nothing
    assert any(m["is_internal"] for m in note["messages"])
    theirs = client.get(f"{P}/{qid}", headers=participant_headers).json()["data"]
    assert [m["body"] for m in theirs["messages"]] == ["My token fails on every call."]
    assert theirs["message_count"] == 1


def test_a_closed_ticket_takes_no_replies_until_reopened(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)

    closed = client.post(f"{P}/{qid}/close", headers=participant_headers).json()["data"]
    assert closed["status"] == 3 and closed["closed_date"]
    assert closed["messages"][-1]["author_type"] == "system"
    assert _say(client, participant_headers, qid, "One more thing").status_code == 409

    reopened = _admin_say(client, admin_headers, qid, "Reopened for you.", status=2)
    assert reopened["status"] == 2 and reopened["closed_date"] is None
    assert _say(client, participant_headers, qid, "Thanks").status_code == 200


def test_admin_can_set_the_status_with_an_event_in_the_thread(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)

    response = client.post(f"{A}/{qid}/status", headers=admin_headers, json={"status": 1})

    thread = response.json()["data"]
    assert thread["status"] == 1
    assert thread["messages"][-1]["author_type"] == "system"
    assert "In progress" in thread["messages"][-1]["body"]


def test_one_participant_cannot_see_or_write_on_anothers_ticket(client, participant_headers, db_session):
    qid = _ticket(client, participant_headers)
    other = _second_participant(db_session)
    session = _login_participant(client, other.email_id, PARTICIPANT_PASSWORD)
    headers = {"x-access-token": session["access_token"], "x-auth-key": session["auth_key"]}

    assert client.get(f"{P}/{qid}", headers=headers).status_code == 404
    assert _say(client, headers, qid, "hello").status_code == 404
    assert client.post(f"{P}/{qid}/close", headers=headers).status_code == 404


def test_unread_follows_who_wrote_last(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)
    [row] = client.post(f"{A}/list", headers=admin_headers, json={"page": 1, "limit": 10}).json()["data"]["queries"]
    assert row["unread"] is True  # the team has not opened it yet

    client.get(f"{A}/{qid}", headers=admin_headers)
    [row] = client.post(f"{A}/list", headers=admin_headers, json={"page": 1, "limit": 10}).json()["data"]["queries"]
    assert row["unread"] is False and row["message_count"] == 1

    _admin_say(client, admin_headers, qid, "On it.")
    [mine] = client.get(P, headers=participant_headers).json()["data"]
    assert mine["unread"] is True
    client.get(f"{P}/{qid}", headers=participant_headers)
    [mine] = client.get(P, headers=participant_headers).json()["data"]
    assert mine["unread"] is False


def test_sla_counts_from_the_participants_last_message(client, admin_headers, participant_headers, db_session, mails):
    qid = _ticket(client, participant_headers)
    row = db_session.get(ParticipantQuery, qid)
    row.added_date = datetime.now(UTC) - timedelta(hours=settings.SUPPORT_SLA_HOURS + 5)
    db_session.commit()
    [late] = client.get(P, headers=participant_headers).json()["data"]
    assert late["is_overdue"] is True

    _admin_say(client, admin_headers, qid, "Sorry for the wait.")
    _say(client, participant_headers, qid, "Still failing.")

    [now] = client.get(P, headers=participant_headers).json()["data"]
    # Old ticket, but the clock restarted when they wrote again.
    assert now["status"] == 0 and now["is_overdue"] is False


def test_replies_are_mailed_with_threading_headers(client, admin_headers, participant_headers, db_session, mails):
    qid = _ticket(client, participant_headers)

    _admin_say(client, admin_headers, qid, "First answer.")
    _say(client, participant_headers, qid, "More detail.")
    _admin_say(client, admin_headers, qid, "Second answer.")

    first, second = [m for m in mails if m["code"] == "QUERY_RESPONSE"]
    assert first["values"]["ticket_no"] == f"TKT-{qid:06d}"
    assert first["values"]["response"] == "First answer." and first["values"]["ticket_url"]
    assert first["headers"]["Message-ID"].startswith("<tkt-")
    assert "In-Reply-To" not in first["headers"]
    # The second mail answers the first one: a mail client keeps them together.
    assert second["headers"]["In-Reply-To"] == first["headers"]["Message-ID"]
    messages = {m.body: m for m in db_session.query(ParticipantQueryMessage).all()}
    assert messages["First answer."].external_id == first["headers"]["Message-ID"]
    assert messages["First answer."].notified_date is not None


def test_support_mailbox_is_told_when_a_participant_writes(client, participant_headers, mails, monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_NOTIFY_EMAIL", "support@example.org")

    qid = _ticket(client, participant_headers)
    _say(client, participant_headers, qid, "Any news?")

    notices = [m for m in mails if m["code"] == "QUERY_NEW_MESSAGE"]
    assert [n["to"] for n in notices] == ["support@example.org"] * 2
    assert notices[1]["values"]["message"] == "Any news?"


def test_no_support_mail_without_a_mailbox(client, participant_headers, mails):
    qid = _ticket(client, participant_headers)
    _say(client, participant_headers, qid, "Any news?")

    assert mails == []


def test_a_mail_failure_does_not_lose_the_reply(client, admin_headers, participant_headers, monkeypatch):
    def _broken(*args, **kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("app.services.support_service.send_templated", _broken)
    qid = _ticket(client, participant_headers)

    thread = _admin_say(client, admin_headers, qid, "Answer despite the outage.")

    assert thread["messages"][-1]["body"] == "Answer despite the outage."
    assert thread["messages"][-1]["notified_date"] is None


def test_the_old_respond_api_adds_a_message(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)

    response = client.post(f"{A}/respond", headers=admin_headers, json={"query_id": qid, "response": "Done.", "status": 3})

    assert response.status_code == 200, response.text
    thread = client.get(f"{P}/{qid}", headers=participant_headers).json()["data"]
    assert thread["status"] == 3 and thread["response"] == "Done."
    assert _roles(thread) == ["participant", "admin"]


def test_a_ticket_has_a_message_limit(client, participant_headers, monkeypatch):
    monkeypatch.setattr(settings, "SUPPORT_MAX_MESSAGES_PER_TICKET", 2)
    qid = _ticket(client, participant_headers)

    assert _say(client, participant_headers, qid, "second").status_code == 200
    assert _say(client, participant_headers, qid, "third").status_code == 409


def test_answered_tickets_close_by_themselves_after_the_wait(client, admin_headers, participant_headers, db_session, monkeypatch, mails):
    monkeypatch.setattr(settings, "SUPPORT_AUTO_CLOSE_DAYS", 7)
    waiting, fresh = _ticket(client, participant_headers, "Old"), _ticket(client, participant_headers, "New")
    _admin_say(client, admin_headers, waiting, "Answer")
    _admin_say(client, admin_headers, fresh, "Answer")
    db_session.get(ParticipantQuery, waiting).last_message_date = datetime.now(UTC) - timedelta(days=8)
    db_session.commit()

    assert support_service.close_stale_tickets(db_session) == 1

    assert db_session.get(ParticipantQuery, waiting).status == 3
    assert db_session.get(ParticipantQuery, fresh).status == 2


def test_auto_close_is_off_by_default(db_session):
    assert settings.SUPPORT_AUTO_CLOSE_DAYS == 0
    assert support_service.close_stale_tickets(db_session) == 0


def test_my_data_export_holds_the_conversation_without_staff_notes(client, admin_headers, participant_headers, mails):
    qid = _ticket(client, participant_headers)
    _admin_say(client, admin_headers, qid, "Public answer.")
    _admin_say(client, admin_headers, qid, "Secret staff note.", internal=True)

    data = client.get("/oan/participant/profile/export", headers=participant_headers).json()["data"]

    [ticket] = data["support_queries"]
    assert [m["body"] for m in ticket["messages"]] == ["My token fails on every call.", "Public answer."]
