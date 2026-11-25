"""Machine-to-machine endpoints, called by infrastructure rather than people.

``POST /internal/gateway/logs`` is the callback APISIX's ``http-logger``
posts call records to (see ``gateway_log_service``). It exists only while
GATEWAY_LOG_INGEST_ENABLED is on and requires
``Authorization: Bearer <GATEWAY_LOG_INGEST_TOKEN>``.
"""

from __future__ import annotations

import hmac
import json

from fastapi import APIRouter, Header, Request

from app.config.settings import settings
from app.core.deps import DbSession
from app.core.exceptions import NotFoundError, UnauthorizedError, ValidationError
from app.core.responses import ok
from app.services import gateway_log_service

router = APIRouter(prefix="/internal", tags=["Internal"])


@router.post("/gateway/logs", include_in_schema=False)
async def gateway_logs(
    request: Request, db: DbSession, authorization: str | None = Header(None)
):
    if not settings.GATEWAY_LOG_INGEST_ENABLED or not settings.GATEWAY_LOG_INGEST_TOKEN:
        raise NotFoundError("Not found.")
    expected = f"Bearer {settings.GATEWAY_LOG_INGEST_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization.encode(), expected.encode()):
        raise UnauthorizedError("Invalid log ingest token.")
    try:
        payload = json.loads(await request.body() or b"[]")
    except ValueError:
        raise ValidationError("The body must be JSON.") from None
    records = payload if isinstance(payload, list) else [payload]
    return ok("Gateway logs received.", gateway_log_service.ingest(db, records))
