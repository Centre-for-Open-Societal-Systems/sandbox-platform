"""Reusable field validators.

The reference stack hard-coded Indian formats (PAN, GSTIN, CIN, IFSC, 6-digit
PIN). OAN dispatches on country instead, so a new member country is onboarded
by adding an entry to ``COUNTRY_RULES`` rather than editing call sites.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.config.settings import settings

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
NAME_RE = re.compile(r"^[A-Za-zሀ-፿][A-Za-zሀ-፿ '.\-]*$")


@dataclass(frozen=True)
class CountryRules:
    """Per-country formats for the fields that vary between members."""

    dial_code: str
    #: National significant number length, excluding the dial code.
    msisdn_length: int
    postal_code_re: re.Pattern | None
    #: Business registration number, e.g. Ethiopia's trade licence number.
    registration_re: re.Pattern | None
    #: Tax identification number.
    tin_re: re.Pattern | None
    #: Human-readable hints surfaced in validation messages.
    labels: dict[str, str] = field(default_factory=dict)


COUNTRY_RULES: dict[str, CountryRules] = {
    "ET": CountryRules(
        dial_code="251",
        msisdn_length=9,  # 9xxxxxxxx / 7xxxxxxxx
        postal_code_re=re.compile(r"^\d{4}$"),
        registration_re=re.compile(r"^[A-Z0-9/\-]{6,20}$"),
        tin_re=re.compile(r"^\d{10}$"),
        labels={"tin": "TIN", "registration": "Trade licence number"},
    ),
    "KE": CountryRules(
        dial_code="254",
        msisdn_length=9,
        postal_code_re=re.compile(r"^\d{5}$"),
        registration_re=re.compile(r"^[A-Z0-9/\-]{6,20}$"),
        tin_re=re.compile(r"^[A-Z]\d{9}[A-Z]$"),  # KRA PIN
        labels={"tin": "KRA PIN", "registration": "Registration number"},
    ),
    "RW": CountryRules(
        dial_code="250",
        msisdn_length=9,
        postal_code_re=None,
        registration_re=re.compile(r"^\d{9}$"),
        tin_re=re.compile(r"^\d{9}$"),
        labels={"tin": "TIN", "registration": "RDB registration number"},
    ),
    "GH": CountryRules(
        dial_code="233",
        msisdn_length=9,
        postal_code_re=None,
        registration_re=re.compile(r"^[A-Z]{2}\d{6,12}$"),
        tin_re=re.compile(r"^[A-Z]\d{10}$"),
        labels={"tin": "TIN", "registration": "Registration number"},
    ),
    "NG": CountryRules(
        dial_code="234",
        msisdn_length=10,
        postal_code_re=re.compile(r"^\d{6}$"),
        registration_re=re.compile(r"^(RC|BN)\d{4,10}$"),
        tin_re=re.compile(r"^\d{8}-\d{4}$"),
        labels={"tin": "TIN", "registration": "CAC number"},
    ),
}

#: Permissive fallback so an un-onboarded country never hard-blocks signup.
DEFAULT_RULES = CountryRules(
    dial_code="",
    msisdn_length=0,
    postal_code_re=None,
    registration_re=re.compile(r"^[A-Za-z0-9/\-]{4,30}$"),
    tin_re=re.compile(r"^[A-Za-z0-9\-]{5,20}$"),
    labels={"tin": "Tax id", "registration": "Registration number"},
)


def rules_for(country_code: str | None = None) -> CountryRules:
    code = (country_code or settings.DEFAULT_COUNTRY_CODE).upper()
    return COUNTRY_RULES.get(code, DEFAULT_RULES)


# ----------------------------------------------------------------- generic
def validate_password_strength(value: str) -> str:
    """Upper + lower + digit + symbol, min 8. Raises ``ValueError`` if weak."""
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain an uppercase letter.")
    if not any(c.islower() for c in value):
        raise ValueError("Password must contain a lowercase letter.")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain a digit.")
    if all(c.isalnum() for c in value):
        raise ValueError("Password must contain a special character.")
    return value


def is_valid_email(value: str | None) -> bool:
    return bool(value and EMAIL_RE.match(value.strip()))


def is_valid_url(value: str | None) -> bool:
    return bool(value and URL_RE.match(value.strip()))


def is_valid_name(value: str | None) -> bool:
    """Accepts Latin and Ethiopic scripts, apostrophes, dots and hyphens."""
    return bool(value and NAME_RE.match(value.strip()))


def sanitize_text(value: str | None) -> str:
    """Collapse whitespace and strip control characters."""
    if not value:
        return ""
    cleaned = "".join(ch for ch in value if ch == "\n" or ch >= " ")
    return re.sub(r"[ \t]+", " ", cleaned).strip()


# --------------------------------------------------------- country-specific
def normalise_msisdn(value: str, country_code: str | None = None) -> str:
    """Return the phone number in E.164 form (``+251911234567``).

    Accepts local (``0911234567``), national (``911234567``) and already
    international inputs.
    """
    rules = rules_for(country_code)
    digits = re.sub(r"[^\d+]", "", value or "")
    if not digits:
        raise ValueError("Mobile number is required.")

    if digits.startswith("+"):
        digits = digits[1:]
    if rules.dial_code:
        if digits.startswith(rules.dial_code):
            national = digits[len(rules.dial_code) :]
        else:
            national = digits.lstrip("0")
        if rules.msisdn_length and len(national) != rules.msisdn_length:
            raise ValueError(
                f"Mobile number must be {rules.msisdn_length} digits after the "
                f"country code (+{rules.dial_code})."
            )
        return f"+{rules.dial_code}{national}"

    if not 6 <= len(digits) <= 15:
        raise ValueError("Mobile number is not valid.")
    return f"+{digits}"


def validate_registration_number(value: str, country_code: str | None = None) -> str:
    rules = rules_for(country_code)
    candidate = (value or "").strip().upper()
    if rules.registration_re and not rules.registration_re.match(candidate):
        label = rules.labels.get("registration", "Registration number")
        raise ValueError(f"{label} format is not valid.")
    return candidate


def validate_tin(value: str, country_code: str | None = None) -> str:
    rules = rules_for(country_code)
    candidate = (value or "").strip().upper()
    if rules.tin_re and not rules.tin_re.match(candidate):
        label = rules.labels.get("tin", "Tax id")
        raise ValueError(f"{label} format is not valid.")
    return candidate


def validate_postal_code(value: str, country_code: str | None = None) -> str:
    rules = rules_for(country_code)
    candidate = (value or "").strip()
    if rules.postal_code_re and not rules.postal_code_re.match(candidate):
        raise ValueError("Postal code format is not valid.")
    return candidate
