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
#: Per-request values filled in by dependencies. A dict (set once by the
#: middleware) because sync dependencies run in a copied context: a plain
#: ``ContextVar.set`` there would not reach the endpoint, a shared dict does.
request_state_ctx: ContextVar[dict | None] = ContextVar("request_state", default=None)


def set_admin_country(country_code: str | None) -> None:
    """Member country the signed-in administrator is limited to (None = all)."""
    state = request_state_ctx.get()
    if state is not None:
        state["admin_country"] = country_code or None


def current_correlation_id() -> str:
    return correlation_id_ctx.get()


def current_client_ip() -> str:
    return client_ip_ctx.get()


def admin_country_scope() -> str | None:
    """Country the current administrator may see participant data of, or None for all."""
    state = request_state_ctx.get()
    return state.get("admin_country") if state else None


def assert_in_admin_scope(country_code: str | None) -> bool:
    """False when the record belongs to a country outside the administrator's scope."""
    scope = admin_country_scope()
    return scope is None or (country_code or "").upper() == scope.upper()


def current_actor() -> tuple[str, str]:
    """Return ``(actor_type, actor_id)`` for the in-flight request."""
    return actor_type_ctx.get(), actor_id_ctx.get()
