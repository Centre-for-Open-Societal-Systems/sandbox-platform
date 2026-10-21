"""CMS administration: FAQs, terms, email templates and home page blocks."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query

from app.core.deps import AdminPrincipal, DbSession, require_permission
from app.core.permissions import Permission
from app.core.responses import ok
from app.schemas.common import ListQuery, ToggleRequest
from app.schemas.content import (
    EmailTemplateUpsert,
    FaqCreate,
    FaqTypeCreate,
    FaqTypeUpdate,
    FaqUpdate,
    HomeBlockUpsertForm,
    TermCreate,
    TermUpdate,
    TestMailRequest,
)
from app.services import content_service
from app.services.notification_service import send_email, send_templated
from app.utils.files import save_upload

router = APIRouter(tags=["Admin / Content"])

ManageContent = Annotated[AdminPrincipal, Depends(require_permission(Permission.CMS))]
ManageFaqTypes = Annotated[
    AdminPrincipal, Depends(require_permission(Permission.FAQ_TYPE))
]

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "svg"}


# ----------------------------------------------------------- faq types
@router.post("/faq-types/list")
def list_faq_types(payload: ListQuery, admin: ManageFaqTypes, db: DbSession):
    return ok(
        "FAQ categories loaded.",
        content_service.list_faq_types(db, payload).as_dict("types"),
    )


@router.get("/faq-types/dropdown")
def faq_type_dropdown(admin: ManageContent, db: DbSession, locale: str = Query("en")):
    return ok("FAQ categories loaded.", content_service.faq_type_dropdown(db, locale))


@router.post("/faq-types")
def create_faq_type(payload: FaqTypeCreate, admin: ManageFaqTypes, db: DbSession):
    row = content_service.create_faq_type(db, admin, payload)
    return ok("FAQ category created successfully.", row.model_dump())


@router.put("/faq-types")
def update_faq_type(payload: FaqTypeUpdate, admin: ManageFaqTypes, db: DbSession):
    row = content_service.update_faq_type(db, admin, payload)
    return ok("FAQ category updated successfully.", row.model_dump())


@router.post("/faq-types/toggle")
def toggle_faq_type(payload: ToggleRequest, admin: ManageFaqTypes, db: DbSession):
    row = content_service.toggle_faq_type(db, admin, payload.id, payload.is_enabled)
    return ok("FAQ category status updated.", row.model_dump())


@router.delete("/faq-types/{type_id}")
def delete_faq_type(type_id: int, admin: ManageFaqTypes, db: DbSession):
    content_service.delete_faq_type(db, admin, type_id)
    return ok("FAQ category deleted successfully.")


# ---------------------------------------------------------------- faqs
@router.post("/faqs/list")
def list_faqs(
    payload: ListQuery,
    admin: ManageContent,
    db: DbSession,
    type_id: int | None = Query(None),
):
    return ok(
        "FAQs loaded.", content_service.list_faqs(db, payload, type_id).as_dict("faqs")
    )


@router.post("/faqs")
def create_faq(payload: FaqCreate, admin: ManageContent, db: DbSession):
    row = content_service.create_faq(db, admin, payload)
    return ok("FAQ created successfully.", row.model_dump())


@router.put("/faqs")
def update_faq(payload: FaqUpdate, admin: ManageContent, db: DbSession):
    row = content_service.update_faq(db, admin, payload)
    return ok("FAQ updated successfully.", row.model_dump())


@router.post("/faqs/toggle")
def toggle_faq(payload: ToggleRequest, admin: ManageContent, db: DbSession):
    row = content_service.toggle_faq(db, admin, payload.id, payload.is_enabled)
    return ok("FAQ status updated.", row.model_dump())


@router.delete("/faqs/{faq_id}")
def delete_faq(faq_id: int, admin: ManageContent, db: DbSession):
    content_service.delete_faq(db, admin, faq_id)
    return ok("FAQ deleted successfully.")


# --------------------------------------------------- terms and conditions
@router.post("/terms/list")
def list_terms(payload: ListQuery, admin: ManageContent, db: DbSession):
    return ok(
        "Content sections loaded.",
        content_service.list_terms(db, payload).as_dict("terms"),
    )


@router.post("/terms")
def create_term(payload: TermCreate, admin: ManageContent, db: DbSession):
    row = content_service.create_term(db, admin, payload)
    return ok("Content section created successfully.", row.model_dump())


@router.put("/terms")
def update_term(payload: TermUpdate, admin: ManageContent, db: DbSession):
    row = content_service.update_term(db, admin, payload)
    return ok("Content section updated successfully.", row.model_dump())


@router.post("/terms/toggle")
def toggle_term(payload: ToggleRequest, admin: ManageContent, db: DbSession):
    row = content_service.toggle_term(db, admin, payload.id, payload.is_enabled)
    return ok("Content section status updated.", row.model_dump())


@router.delete("/terms/{table_id}")
def delete_term(table_id: int, admin: ManageContent, db: DbSession):
    content_service.delete_term(db, admin, table_id)
    return ok("Content section deleted successfully.")


# ------------------------------------------------------- email templates
@router.post("/email-templates/list")
def list_email_templates(payload: ListQuery, admin: ManageContent, db: DbSession):
    page = content_service.list_email_templates(db, payload)
    return ok("Email templates loaded.", page.as_dict("templates"))


@router.get("/email-templates/{template_id}")
def get_email_template(template_id: int, admin: ManageContent, db: DbSession):
    row = content_service.get_email_template(db, template_id)
    return ok("Email template loaded.", row.model_dump())


@router.post("/email-templates")
def upsert_email_template(
    payload: EmailTemplateUpsert, admin: ManageContent, db: DbSession
):
    row = content_service.upsert_email_template(db, admin, payload)
    return ok("Email template saved successfully.", row.model_dump())


@router.post("/email-templates/test")
def send_test_mail(payload: TestMailRequest, admin: ManageContent, db: DbSession):
    """Verify SMTP configuration by sending one message."""
    if payload.template_code:
        sent = send_templated(
            db, payload.template_code, payload.to_email, {"name": "Test User"}
        )
    else:
        sent = send_email(
            payload.to_email, payload.subject or "OAN test", payload.body or "Test"
        )

    message = (
        "Test email sent." if sent else "Mail delivery is disabled or not configured."
    )
    return ok(message, {"sent": sent})


# ------------------------------------------------------------- home page
@router.get("/home-blocks")
def list_home_blocks(admin: ManageContent, db: DbSession, locale: str = Query("en")):
    rows = content_service.list_home_blocks(db, locale)
    return ok("Home page blocks loaded.", [row.model_dump() for row in rows])


@router.post("/home-blocks")
async def upsert_home_block(
    admin: ManageContent,
    db: DbSession,
    payload: Annotated[HomeBlockUpsertForm, Form()],
):
    image_path = (
        (await save_upload(payload.image, "home", IMAGE_EXTENSIONS)).path
        if payload.image
        else None
    )
    row = content_service.upsert_home_block(db, admin, payload, image_path)
    return ok("Home page block saved successfully.", row.model_dump())


@router.delete("/home-blocks/{block_id}")
def delete_home_block(block_id: int, admin: ManageContent, db: DbSession):
    content_service.delete_home_block(db, admin, block_id)
    return ok("Home page block deleted successfully.")
