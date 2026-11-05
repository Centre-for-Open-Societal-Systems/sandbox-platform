"""Store the call records APISIX reports for app keys (the logs callback).

Each app's consumer carries ``http-logger`` (``app_gateway_service``), which
posts batches of ``LOG_FORMAT`` records to ``POST /internal/gateway/logs``.
They become API history rows with ``source`` DIRECT, so a participant sees
the calls their own servers make, not only the ones made from try-it.

* only consumers of sandbox apps (``oanapp_*``) are stored;
* try-it calls carry ``X-OAN-Sandbox-Transaction`` and are skipped: the
  sandbox has already recorded them, with request and response bodies;
* APISIX's request id is unique, so a batch delivered twice is stored once;
* the endpoint is found from method + path (``/v1/leads/{id}`` matches
  ``/v1/leads/L-1``); a call to a path the catalogue does not know is still
  stored, without an endpoint.

No credentials are in the records: ``LOG_FORMAT`` carries no header but the
user agent.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logging import get_logger
from app.models.app import ParticipantApp
from app.models.catalog import Endpoint, Product
from app.models.enums import ApiCallSource, Environment
from app.models.logs import ApiLog
from app.models.participant import Participant
from app.services.sandbox_service import gateway_url, public_url

logger = get_logger(__name__)

CONSUMER_PREFIX = "oanapp_"
_PARAM = re.compile(r"\\\{[^/]*?\\\}")


def ingest(db: Session, records: list[dict[str, Any]]) -> dict[str, int]:
    """Store a batch; returns how many rows were stored and skipped."""
    wanted = [
        r
        for r in records
        if isinstance(r, dict)
        and str(r.get("consumer") or "").startswith(CONSUMER_PREFIX)
        and not r.get("sandbox_txn")
        and r.get("request_id")
    ]
    skipped = len(records) - len(wanted)
    if not wanted:
        return {"stored": 0, "skipped": skipped}

    request_ids = {str(r["request_id"])[:64] for r in wanted}
    seen = set(
        db.execute(
            select(ApiLog.gateway_request_id).where(ApiLog.gateway_request_id.in_(request_ids))
        ).scalars()
    )
    rows = db.execute(
        select(ParticipantApp, Participant)
        .join(Participant, Participant.participant_id == ParticipantApp.participant_id)
        .where(ParticipantApp.gateway_consumer.in_({str(r["consumer"]) for r in wanted}))
    ).all()
    apps = {app.gateway_consumer: (app, participant) for app, participant in rows}
    matcher = _EndpointMatcher(db)

    stored = 0
    for record in wanted:
        request_id = str(record["request_id"])[:64]
        owner = apps.get(str(record["consumer"]))
        if request_id in seen or owner is None:
            skipped += 1
            continue
        seen.add(request_id)
        db.add(_row(record, request_id, *owner, matcher))
        stored += 1
    db.commit()
    return {"stored": stored, "skipped": skipped}


def _without_key(query: str) -> str:
    """The query string minus an API key a caller passed as a parameter."""
    if not query:
        return query
    pairs = parse_qsl(query, keep_blank_values=True)
    key_names = {settings.GATEWAY_APP_KEY_HEADER.lower(), "apikey", "api_key", "key", "token", "access_token"}
    return urlencode([(k, "***" if k.lower() in key_names else v) for k, v in pairs], safe="*")


def _row(
    record: dict[str, Any],
    request_id: str,
    app: ParticipantApp,
    participant: Participant,
    matcher: _EndpointMatcher,
) -> ApiLog:
    method = str(record.get("method") or "").upper() or None
    path = str(record.get("uri") or "")
    query = _without_key(str(record.get("query") or ""))
    status = _int(record.get("status"))
    seconds = _float(record.get("request_time"))
    upstream = _upstream_seconds(record.get("upstream_time"))
    started = _time(record.get("time"))
    try:
        environment = Environment(app.environment)
    except ValueError:
        environment = Environment.UAT
    endpoint = matcher.find(method, path)
    internal = gateway_url(environment)
    base = public_url(internal, environment).rstrip("/") if internal else ""
    shown = path + (f"?{query}" if query else "")
    return ApiLog(
        source=str(ApiCallSource.DIRECT),
        gateway_request_id=request_id,
        transaction_id=request_id,
        app_id=app.app_id,
        participant_id=participant.participant_id,
        entity_id=participant.uat_entity_id or participant.prod_entity_id,
        product_id=endpoint.product_id if endpoint else None,
        endpoint_id=endpoint.endpoint_id if endpoint else None,
        environment=str(environment),
        country_code=participant.country_code,
        method=method,
        endpoint_url=endpoint.endpoint_url if endpoint else path,
        target_url=f"{base}{shown}" if base else shown,
        status_code=status,
        error_message=_gateway_error(status),
        request_time=started,
        response_time=started + timedelta(seconds=seconds or 0) if started else None,
        latency_ms=round(seconds * 1000, 2) if seconds is not None else None,
        upstream_latency_ms=round(upstream * 1000, 2) if upstream is not None else None,
        client_ip=str(record.get("client_ip") or "")[:45] or None,
        request_size=_int(record.get("request_length")),
        response_size=_int(record.get("bytes_sent")),
        request_headers={"User-Agent": str(record["user_agent"])[:500]} if record.get("user_agent") else None,
    )


class _EndpointMatcher:
    """Catalogue endpoints served through the gateway, matched by method + path."""

    def __init__(self, db: Session) -> None:
        endpoints = db.execute(
            select(Endpoint)
            .join(Product, Product.product_id == Endpoint.product_id)
            .where(
                Endpoint.is_deleted.is_(False),
                or_(Endpoint.is_gateway_published.is_(True), Product.is_gateway_published.is_(True)),
            )
        ).scalars()
        patterns = []
        for endpoint in endpoints:
            url = (endpoint.endpoint_url or "").rstrip("/") or "/"
            regex = re.compile("^" + _PARAM.sub("[^/]+", re.escape(url)) + "/?$")
            # Fixed paths before templated ones: /v1/leads/export beats /v1/leads/{id}.
            patterns.append((url.count("{"), (endpoint.method or "").upper(), regex, endpoint))
        self._patterns = sorted(patterns, key=lambda item: item[0])

    def find(self, method: str | None, path: str) -> Endpoint | None:
        for _, endpoint_method, regex, endpoint in self._patterns:
            if endpoint_method == (method or "") and regex.match(path):
                return endpoint
        return None


def _gateway_error(status: int | None) -> str | None:
    return {
        401: "Rejected by the gateway or the API: not authenticated.",
        403: "Rejected: no access (API product, IP whitelist or the API itself).",
        429: "Rate limit exceeded.",
    }.get(status or 0)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _upstream_seconds(value: Any) -> float | None:
    # "0.012" or, after retries, "0.010, 0.020": the sum is the time spent upstream.
    if value in (None, ""):
        return None
    parts = [_float(part.strip()) for part in str(value).split(",")]
    numbers = [p for p in parts if p is not None]
    return sum(numbers) if numbers else None


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
