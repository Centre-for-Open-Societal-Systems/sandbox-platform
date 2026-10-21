"""HTTP middleware: correlation ids, client IP capture and access logging."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.context import (
    actor_id_ctx,
    actor_type_ctx,
    client_ip_ctx,
    correlation_id_ctx,
)
from app.core.logging import get_logger

logger = get_logger("app.access")

CORRELATION_HEADER = "x-correlation-id"


def get_client_ip(request: Request) -> str:
    """Resolve the caller IP, honouring the proxy chain in front of the app."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else ""


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Seed the request-scoped context vars and emit one access log line."""

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(CORRELATION_HEADER) or str(uuid.uuid4())
        tokens = [
            correlation_id_ctx.set(correlation_id),
            client_ip_ctx.set(get_client_ip(request)),
            actor_id_ctx.set(""),
            actor_type_ctx.set("anonymous"),
        ]
        request.state.correlation_id = correlation_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            for var, token in zip(
                (correlation_id_ctx, client_ip_ctx, actor_id_ctx, actor_type_ctx),
                tokens,
                strict=True,
            ):
                var.reset(token)

        response.headers[CORRELATION_HEADER] = correlation_id
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={"correlation_id": correlation_id},
        )
        return response


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestContextMiddleware)
