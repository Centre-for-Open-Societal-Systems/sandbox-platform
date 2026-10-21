"""Small shared helpers.

Ports the grab-bag in ``utilities/common.js`` and ``utilities/commonUtils.js``.
"""

from __future__ import annotations

import re
import secrets
import string
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

REFERENCE_ALPHABET = string.ascii_uppercase + string.digits


def utcnow() -> datetime:
    return datetime.now(UTC)


def generate_reference(prefix: str, length: int = 10) -> str:
    """Human-quotable id, e.g. ``TXN-7HJ2K9QW3M``.

    Used for sandbox transactions and batch jobs - anything a person might have
    to read aloud or paste into a support ticket.
    """
    body = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(length))
    return f"{prefix}-{body}"


def mask_email(value: str | None) -> str:
    if not value or "@" not in value:
        return ""
    local, _, domain = value.partition("@")
    if len(local) <= 2:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}{'*' * (len(local) - 2)}@{domain}"


def mask_mobile(value: str | None) -> str:
    if not value:
        return ""
    digits = re.sub(r"\D", "", value)
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"{'*' * (len(digits) - 4)}{digits[-4:]}"


def to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def to_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def chunked(items: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def dict_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Field-level change set for the audit trail."""
    changes: dict[str, Any] = {}
    for key in set(before) | set(after):
        old, new = before.get(key), after.get(key)
        if old != new:
            changes[key] = {"from": old, "to": new}
    return changes


def render_template(text: str | None, variables: dict[str, Any]) -> str:
    """Substitute ``{{name}}`` placeholders.

    Deliberately not Jinja: templates are edited by admins in a rich-text box,
    so expression evaluation would be an injection surface.
    """
    if not text:
        return ""

    def _replace(match: re.Match) -> str:
        key = match.group(1).strip()
        return str(variables.get(key, match.group(0)))

    return re.sub(r"\{\{\s*([\w.]+)\s*\}\}", _replace, text)


def extract_placeholders(text: str | None) -> list[str]:
    if not text:
        return []
    return sorted(
        {m.group(1).strip() for m in re.finditer(r"\{\{\s*([\w.]+)\s*\}\}", text)}
    )


def safe_json(value: Any, default: Any = None) -> Any:
    """Coerce a value into something JSON-serialisable for log columns."""
    import json

    if value is None:
        return default
    if isinstance(value, (dict, list, str, int, float, bool)):
        return value
    try:
        return json.loads(json.dumps(value, default=str))
    except (TypeError, ValueError):
        return str(value)


def truncate(value: str | None, length: int = 200) -> str:
    if not value:
        return ""
    return value if len(value) <= length else f"{value[: length - 1]}…"
