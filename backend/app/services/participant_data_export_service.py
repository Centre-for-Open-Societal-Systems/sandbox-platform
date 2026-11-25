"""A participant's own data as one JSON document (the "download my data" right).

Covers what the sandbox holds about the account: profile, apps (key prefixes only -
never a key or a secret), support queries, API call history and the audit trail of
the participant's own actions. Passwords, tokens, private keys and one-time codes
are never included.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import ParticipantPrincipal
from app.models.logs import ApiLog, UserActionLog
from app.repositories.participant_repository import (
    ParticipantQueryMessageRepository,
    ParticipantQueryRepository,
)
from app.schemas.participant import ParticipantOut, QueryMessageOut, QueryOut
from app.services import app_service, audit_service
from app.services.audit_service import Action

#: Rows of each log kind in the file (the newest ones).
LOG_ROW_LIMIT = 5000


def _api_calls(db: Session, participant_id: int) -> list[dict[str, Any]]:
    stmt = (
        select(ApiLog)
        .where(ApiLog.participant_id == participant_id)
        .order_by(ApiLog.log_timestamp.desc())
        .limit(LOG_ROW_LIMIT)
    )
    return [
        {
            "time": row.request_time or row.log_timestamp,
            "source": row.source,
            "environment": row.environment,
            "method": row.method,
            "url": row.endpoint_url,
            "status_code": row.status_code,
            "latency_ms": row.latency_ms,
            "app_id": row.app_id,
        }
        for row in db.execute(stmt).scalars()
    ]


def _own_actions(db: Session, participant_id: int) -> list[dict[str, Any]]:
    stmt = (
        select(UserActionLog)
        .where(UserActionLog.actor_type == "participant", UserActionLog.actor_id == str(participant_id))
        .order_by(UserActionLog.timestamp.desc())
        .limit(LOG_ROW_LIMIT)
    )
    return [
        {"time": row.timestamp, "action": row.action, "entity": row.entity, "description": row.description}
        for row in db.execute(stmt).scalars()
    ]


def export_participant_data(db: Session, principal: ParticipantPrincipal) -> dict[str, Any]:
    participant = principal.participant
    messages = ParticipantQueryMessageRepository(db)
    apps = app_service.list_apps(db, participant)
    data = {
        "exported_at": datetime.now(UTC),
        "profile": ParticipantOut.model_validate(participant).model_dump(),
        "apps": [
            # Key prefixes and dates only: a key or a secret never leaves in an export.
            a.model_dump(exclude={"gateway_error"}) | {"credentials": [
                {k: v for k, v in c.model_dump().items() if k not in ("api_key", "api_secret")}
                for c in a.credentials
            ]}
            for a in apps
        ],
        "support_queries": [
            QueryOut.model_validate(row).model_dump()
            | {"messages": [QueryMessageOut.model_validate(m).model_dump() for m in messages.thread(row.query_id, False)]}
            for row in ParticipantQueryRepository(db).list_all(participant_id=principal.id)
        ],
        "api_calls": _api_calls(db, participant.participant_id),
        "account_activity": _own_actions(db, participant.participant_id),
        "notes": f"API calls and activity: the newest {LOG_ROW_LIMIT} of each.",
    }
    audit_service.record_participant(
        db, principal, Action.EXPORT, entity="participant", entity_id=participant.participant_id,
        description="Downloaded own account data",
    )
    return data
