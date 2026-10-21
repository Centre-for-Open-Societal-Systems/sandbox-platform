"""Per-request context.

Gives services access to the correlation id and caller identity without
threading ``Request`` through every layer - the equivalent of the reference
stack's ``express-correlation-id`` middleware.
"""

from contextvars import ContextVar

correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")
actor_id_ctx: ContextVar[str] = ContextVar("actor_id", default="")
actor_type_ctx: ContextVar[str] = ContextVar("actor_type", default="anonymous")
client_ip_ctx: ContextVar[str] = ContextVar("client_ip", default="")


def current_correlation_id() -> str:
    return correlation_id_ctx.get()


def current_client_ip() -> str:
    return client_ip_ctx.get()


def current_actor() -> tuple[str, str]:
    """Return ``(actor_type, actor_id)`` for the in-flight request."""
    return actor_type_ctx.get(), actor_id_ctx.get()
