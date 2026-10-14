"""CMS content: FAQs, terms, email templates and home page blocks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.deps import AdminPrincipal
from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import Page
from app.repositories.catalog_repository import ProductRepository
from app.repositories.content_repository import (
    EmailTemplateRepository,
    FaqRepository,
    FaqTypeRepository,
    HomeBlockRepository,
    TermRepository,
)
from app.repositories.master_repository import CountryRepository
from app.repositories.participant_repository import ParticipantRepository
from app.schemas.content import (
    EmailTemplateOut,
    EmailTemplateUpsert,
    FaqCreate,
    FaqGroupOut,
    FaqOut,
    FaqTypeCreate,
    FaqTypeOut,
    FaqTypeUpdate,
    FaqUpdate,
    HomeBlockOut,
    HomeBlockUpsert,
    PublicHomeResponse,
    TermCreate,
    TermOut,
    TermUpdate,
)
from app.services import audit_service
from app.services.audit_service import Action
from app.utils.common import extract_placeholders
from app.utils.files import public_url


# --------------------------------------------------------------------- faqs
def list_faq_types(db: Session, query) -> Page:
    repo = FaqTypeRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
    )
    counts = repo.faq_counts([row.type_id for row in page.rows])
    page.rows = [_to_faq_type_out(row, counts) for row in page.rows]
    return page


def faq_type_dropdown(db: Session, locale: str = "en") -> list[dict]:
    return [
        {"label": row.faq_type, "value": row.type_id}
        for row in FaqTypeRepository(db).published(locale)
    ]


def create_faq_type(
    db: Session, admin: AdminPrincipal, payload: FaqTypeCreate
) -> FaqTypeOut:
    repo = FaqTypeRepository(db)
    if repo.exists(faq_type=payload.faq_type, locale=payload.locale):
        raise ConflictError("An FAQ category with this name already exists.")

    row = repo.create(**payload.model_dump(), added_by=admin.id, modify_by=admin.id)
    _audit_content(
        db, admin, Action.CONTENT_UPSERT, "faq_type", row.type_id, payload.faq_type
    )
    return _to_faq_type_out(row, {})


def update_faq_type(
    db: Session, admin: AdminPrincipal, payload: FaqTypeUpdate
) -> FaqTypeOut:
    repo = FaqTypeRepository(db)
    row = repo.get(payload.type_id)
    if row is None:
        raise NotFoundError("FAQ category not found.")

    repo.update(row, **payload.model_dump(exclude={"type_id"}), modify_by=admin.id)
    _audit_content(
        db, admin, Action.CONTENT_UPSERT, "faq_type", row.type_id, row.faq_type
    )
    return _to_faq_type_out(row, repo.faq_counts([row.type_id]))


def toggle_faq_type(
    db: Session, admin: AdminPrincipal, type_id: int, is_enabled: bool | None
) -> FaqTypeOut:
    repo = FaqTypeRepository(db)
    row = repo.get(type_id)
    if row is None:
        raise NotFoundError("FAQ category not found.")
    repo.toggle(row, is_enabled, admin.id)
    return _to_faq_type_out(row, repo.faq_counts([type_id]))


def delete_faq_type(db: Session, admin: AdminPrincipal, type_id: int) -> None:
    repo = FaqTypeRepository(db)
    row = repo.get(type_id)
    if row is None:
        raise NotFoundError("FAQ category not found.")
    if FaqRepository(db).for_type(type_id, only_enabled=False):
        raise ConflictError("Remove the questions in this category before deleting it.")

    repo.soft_delete(row, admin.id)
    _audit_content(db, admin, Action.CONTENT_DELETE, "faq_type", type_id, row.faq_type)


def list_faqs(db: Session, query, type_id: int | None = None) -> Page:
    repo = FaqRepository(db)
    page = repo.paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
        type_id=type_id,
    )
    type_names = repo.type_names([row.type_id for row in page.rows])
    page.rows = [_to_faq_out(row, type_names) for row in page.rows]
    return page


def public_faqs(
    db: Session, locale: str = "en", country_code: str | None = None
) -> list[FaqGroupOut]:
    types = FaqTypeRepository(db).published(locale, country_code)
    faqs = FaqRepository(db)
    return [
        FaqGroupOut(
            type_id=faq_type.type_id,
            faq_type=faq_type.faq_type,
            sort_order=faq_type.sort_order,
            faqs=[
                FaqOut.model_validate(faq) for faq in faqs.for_type(faq_type.type_id)
            ],
        )
        for faq_type in types
    ]


def create_faq(db: Session, admin: AdminPrincipal, payload: FaqCreate) -> FaqOut:
    if FaqTypeRepository(db).get(payload.type_id) is None:
        raise NotFoundError("FAQ category not found.")

    repo = FaqRepository(db)
    row = repo.create(**payload.model_dump(), added_by=admin.id, modify_by=admin.id)
    _audit_content(
        db, admin, Action.CONTENT_UPSERT, "faq_detail", row.faq_id, payload.question
    )
    return _to_faq_out(row, repo.type_names([row.type_id]))


def update_faq(db: Session, admin: AdminPrincipal, payload: FaqUpdate) -> FaqOut:
    repo = FaqRepository(db)
    row = repo.get(payload.faq_id)
    if row is None:
        raise NotFoundError("FAQ not found.")

    repo.update(row, **payload.model_dump(exclude={"faq_id"}), modify_by=admin.id)
    _audit_content(
        db, admin, Action.CONTENT_UPSERT, "faq_detail", row.faq_id, row.question
    )
    return _to_faq_out(row, repo.type_names([row.type_id]))


def toggle_faq(
    db: Session, admin: AdminPrincipal, faq_id: int, is_enabled: bool | None
) -> FaqOut:
    repo = FaqRepository(db)
    row = repo.get(faq_id)
    if row is None:
        raise NotFoundError("FAQ not found.")
    repo.toggle(row, is_enabled, admin.id)
    return _to_faq_out(row, repo.type_names([row.type_id]))


def delete_faq(db: Session, admin: AdminPrincipal, faq_id: int) -> None:
    repo = FaqRepository(db)
    row = repo.get(faq_id)
    if row is None:
        raise NotFoundError("FAQ not found.")
    repo.soft_delete(row, admin.id)
    _audit_content(db, admin, Action.CONTENT_DELETE, "faq_detail", faq_id, row.question)


# ------------------------------------------------------ terms and conditions
def list_terms(db: Session, query) -> Page:
    page = TermRepository(db).paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
    )
    page.rows = [TermOut.model_validate(row) for row in page.rows]
    return page


def public_terms(
    db: Session, locale: str = "en", country_code: str | None = None
) -> list[TermOut]:
    rows = TermRepository(db).published(locale, country_code)
    return [TermOut.model_validate(row) for row in rows]


def create_term(db: Session, admin: AdminPrincipal, payload: TermCreate) -> TermOut:
    row = TermRepository(db).create(
        **payload.model_dump(), added_by=admin.id, modify_by=admin.id
    )
    _audit_content(
        db,
        admin,
        Action.CONTENT_UPSERT,
        "term_condition",
        row.table_id,
        payload.sidebar_title,
    )
    return TermOut.model_validate(row)


def update_term(db: Session, admin: AdminPrincipal, payload: TermUpdate) -> TermOut:
    repo = TermRepository(db)
    row = repo.get(payload.table_id)
    if row is None:
        raise NotFoundError("Content section not found.")

    repo.update(row, **payload.model_dump(exclude={"table_id"}), modify_by=admin.id)
    _audit_content(
        db,
        admin,
        Action.CONTENT_UPSERT,
        "term_condition",
        row.table_id,
        row.sidebar_title,
    )
    return TermOut.model_validate(row)


def toggle_term(
    db: Session, admin: AdminPrincipal, table_id: int, is_enabled: bool | None
) -> TermOut:
    repo = TermRepository(db)
    row = repo.get(table_id)
    if row is None:
        raise NotFoundError("Content section not found.")
    repo.toggle(row, is_enabled, admin.id)
    return TermOut.model_validate(row)


def delete_term(db: Session, admin: AdminPrincipal, table_id: int) -> None:
    repo = TermRepository(db)
    row = repo.get(table_id)
    if row is None:
        raise NotFoundError("Content section not found.")
    repo.soft_delete(row, admin.id)
    _audit_content(
        db, admin, Action.CONTENT_DELETE, "term_condition", table_id, row.sidebar_title
    )


# ----------------------------------------------------------- email templates
def list_email_templates(db: Session, query) -> Page:
    page = EmailTemplateRepository(db).paginate(
        page=query.page,
        limit=query.limit,
        search=query.search,
        sort_by=query.sort_by,
        sort_dir=query.sort_dir,
    )
    page.rows = [EmailTemplateOut.model_validate(row) for row in page.rows]
    return page


def get_email_template(db: Session, template_id: int) -> EmailTemplateOut:
    row = EmailTemplateRepository(db).get(template_id)
    if row is None:
        raise NotFoundError("Email template not found.")
    return EmailTemplateOut.model_validate(row)


def upsert_email_template(
    db: Session, admin: AdminPrincipal, payload: EmailTemplateUpsert
) -> EmailTemplateOut:
    repo = EmailTemplateRepository(db)
    values = payload.model_dump(exclude={"template_id"})
    # Keep the declared variable list in step with the body actually saved.
    values["variables"] = payload.variables or extract_placeholders(payload.body_text)

    if payload.template_id:
        row = repo.get(payload.template_id)
        if row is None:
            raise NotFoundError("Email template not found.")
        repo.set_fields(row, **values, modify_by=admin.id)
    else:
        if repo.get_by_code(payload.template_code, payload.locale):
            raise ConflictError(
                "A template with this code already exists for the locale."
            )
        row = repo.create(**values, added_by=admin.id, modify_by=admin.id)

    _audit_content(
        db,
        admin,
        Action.CONTENT_UPSERT,
        "email_template",
        row.template_id,
        row.template_code,
    )
    return EmailTemplateOut.model_validate(row)


# ------------------------------------------------------------- home page CMS
def list_home_blocks(db: Session, locale: str = "en") -> list[HomeBlockOut]:
    rows = HomeBlockRepository(db).list_all(locale=locale, order_by="sort_order")
    return [_to_home_block_out(row) for row in rows]


def upsert_home_block(
    db: Session,
    admin: AdminPrincipal,
    payload: HomeBlockUpsert,
    image_path: str | None = None,
) -> HomeBlockOut:
    repo = HomeBlockRepository(db)
    values = payload.model_dump(exclude={"block_id"})
    if image_path:
        values["image_path"] = image_path

    if payload.block_id:
        row = repo.get(payload.block_id)
        if row is None:
            raise NotFoundError("Home page block not found.")
        repo.set_fields(row, **values, modify_by=admin.id)
    else:
        row = repo.create(**values, added_by=admin.id, modify_by=admin.id)

    _audit_content(
        db, admin, Action.CONTENT_UPSERT, "home_page_block", row.block_id, row.block_key
    )
    return _to_home_block_out(row)


def delete_home_block(db: Session, admin: AdminPrincipal, block_id: int) -> None:
    repo = HomeBlockRepository(db)
    row = repo.get(block_id)
    if row is None:
        raise NotFoundError("Home page block not found.")
    repo.soft_delete(row, admin.id)


def public_home(
    db: Session, locale: str = "en", country_code: str | None = None
) -> PublicHomeResponse:
    """Everything the public landing page needs, assembled in one call."""
    blocks = HomeBlockRepository(db).published(locale, country_code)
    products = ProductRepository(db)
    featured = list(
        db.execute(products.published_stmt(country_code).limit(6)).scalars().all()
    )
    user_counts = ParticipantRepository(db).counts_by_status(country_code)
    total_products, published_products = products.counts()

    return PublicHomeResponse(
        blocks=[_to_home_block_out(block) for block in blocks],
        stats={
            "users": user_counts["total_participants"],
            "products": published_products,
            "countries": len(CountryRepository(db).live_countries()),
        },
        featured_products=[
            {
                "product_id": product.product_id,
                "product_name": product.display_name or product.product_name,
                "description": product.description,
                "product_icon": public_url(product.product_icon),
            }
            for product in featured
        ],
        countries=[
            {
                "country_code": country.country_code,
                "country_name": country.country_name,
                "is_live": country.is_live,
            }
            for country in CountryRepository(db).live_countries()
        ],
    )


# ------------------------------------------------------------------ helpers
def _to_faq_type_out(row, counts: dict[int, int]) -> FaqTypeOut:
    out = FaqTypeOut.model_validate(row)
    out.faq_count = counts.get(row.type_id, 0)
    return out


def _to_faq_out(row, type_names: dict[int, str]) -> FaqOut:
    out = FaqOut.model_validate(row)
    out.faq_type = type_names.get(row.type_id)
    return out


def _to_home_block_out(row) -> HomeBlockOut:
    out = HomeBlockOut.model_validate(row)
    out.image_path = public_url(row.image_path)
    return out


def _audit_content(
    db: Session,
    admin: AdminPrincipal,
    action: str,
    entity: str,
    entity_id: int,
    label: str,
) -> None:
    audit_service.record_admin(
        db,
        admin,
        action,
        entity=entity,
        entity_id=entity_id,
        description=f"{entity} '{label}'",
    )
