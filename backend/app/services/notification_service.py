"""Email and SMS delivery.

Templates live in the database (``email_template``) so admins can edit copy
without a deploy. When ``MAIL_ENABLED`` is off, messages are logged instead of
sent, which is what local development and CI want.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from typing import Any

from sqlalchemy.orm import Session

from app.config.settings import settings
from app.core.logging import get_logger
from app.repositories.content_repository import EmailTemplateRepository
from app.utils.common import render_template

logger = get_logger(__name__)


class TemplateCode:
    """Template keys the services look up. Seeded in ``seeds/seed_data.py``."""

    PARTICIPANT_WELCOME = "PARTICIPANT_WELCOME"
    PARTICIPANT_OTP = "PARTICIPANT_OTP"
    PARTICIPANT_APPROVED = "PARTICIPANT_APPROVED"
    PARTICIPANT_REJECTED = "PARTICIPANT_REJECTED"
    PARTICIPANT_RESET_PASSWORD = "PARTICIPANT_RESET_PASSWORD"
    PROMOTION_APPROVED = "PROMOTION_APPROVED"
    PROMOTION_REJECTED = "PROMOTION_REJECTED"
    ADMIN_INVITE = "ADMIN_INVITE"
    ADMIN_RESET_PASSWORD = "ADMIN_RESET_PASSWORD"
    QUERY_RESPONSE = "QUERY_RESPONSE"


def send_email(
    to_email: str,
    subject: str,
    body_html: str,
    from_email: str | None = None,
) -> bool:
    """Send one message. Returns True when it actually left the process."""
    if not to_email:
        logger.warning("send_email called with no recipient; skipping.")
        return False

    if not settings.MAIL_ENABLED or not settings.SMTP_HOST:
        logger.info(
            "[mail disabled] to=%s subject=%s\n%s", to_email, subject, body_html[:500]
        )
        return False

    message = EmailMessage()
    message["From"] = from_email or settings.SMTP_FROM
    message["To"] = to_email
    message["Subject"] = subject
    # Plain-text part first so non-HTML clients get something readable.
    message.set_content(_strip_html(body_html))
    message.add_alternative(body_html, subtype="html")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as server:
            if settings.SMTP_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        logger.info("Sent '%s' to %s", subject, to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send '%s' to %s: %s", subject, to_email, exc)
        return False


def send_templated(
    db: Session,
    template_code: str,
    to_email: str,
    variables: dict[str, Any],
    locale: str = "en",
) -> bool:
    """Render a stored template and send it."""
    template = EmailTemplateRepository(db).get_by_code(template_code, locale)
    if template is None:
        logger.warning("Email template '%s' is missing; nothing sent.", template_code)
        return False

    merged = {
        "portal_url": settings.portal_url,
        **variables,
    }
    subject = render_template(template.subject, merged)
    body = render_template(template.body_text, merged)
    return send_email(to_email, subject, body)


def send_sms(mobile_number: str, message: str) -> bool:
    """SMS delivery seam.

    Ethiopia's aggregator differs per deployment, so this stays a stub that
    logs; wire the member country's gateway here.
    """
    logger.info("[sms stub] to=%s message=%s", mobile_number, message)
    return False


def send_otp(
    db: Session,
    otp: str,
    email: str | None = None,
    mobile_number: str | None = None,
    locale: str = "en",
) -> bool:
    """Deliver an OTP over whichever channels are available."""
    delivered = False
    if email:
        delivered = (
            send_templated(
                db,
                TemplateCode.PARTICIPANT_OTP,
                email,
                {"otp": otp, "validity_minutes": settings.OTP_TTL_SECONDS // 60},
                locale,
            )
            or delivered
        )
    if mobile_number:
        delivered = (
            send_sms(
                mobile_number,
                f"Your OAN verification code is {otp}. It expires in "
                f"{settings.OTP_TTL_SECONDS // 60} minutes.",
            )
            or delivered
        )
    if not delivered:
        # Surfaced so a developer can complete signup without a mail server.
        logger.info("OTP for %s / %s is %s", email, mobile_number, otp)
    return delivered


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<br\s*/?>", "\n", html or "")
    text = re.sub(r"</p>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
