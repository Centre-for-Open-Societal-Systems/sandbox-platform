"""Idempotent database seeding.

Run with ``python -m app.seeds.seed``. Every step checks for existing rows, so
re-running against a populated database is safe and only fills in gaps.
"""

from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.core.permissions import PERMISSION_TREE, Permission
from app.core.security import hash_password
from app.models.admin import AdmRole, AdmRolePermission, AdmUser
from app.models.content import (
    EmailTemplate,
    FaqDetail,
    FaqType,
    HomePageBlock,
    TermCondition,
)
from app.models.geo import AdminArea, Country
from app.models.masters import Category, ProductCategory, SubCategory
from app.repositories.admin_repository import PermissionRepository
from app.repositories.master_repository import LOOKUPS, LookupRepository
from app.seeds import reference_data as data
from app.utils.common import extract_placeholders

logger = get_logger(__name__)

SUPER_ROLE = "Super Administrator"
OPERATIONS_ROLE = "Network Operations"
CONTENT_ROLE = "Content Editor"

#: Permission bundles granted to the roles created at install time.
ROLE_GRANTS = {
    OPERATIONS_ROLE: [
        Permission.PARTICIPANT_MANAGEMENT,
        Permission.ALL_PARTICIPANTS,
        Permission.UAT_PARTICIPANTS,
        Permission.UAT_APPROVAL_PENDING,
        Permission.UAT_REJECTED_PARTICIPANTS,
        Permission.PROD_PARTICIPANTS,
        Permission.PROD_APPROVAL_PENDING,
        Permission.PROD_REJECTED_PARTICIPANTS,
        Permission.API_CATALOGUE,
        Permission.AUDIT_LOGS,
        Permission.USER_TRACKING,
        Permission.API_HISTORY,
        Permission.USER_QUERIES,
    ],
    CONTENT_ROLE: [
        Permission.CMS,
        Permission.FAQS,
        Permission.TERMS_AND_CONDITIONS,
        Permission.EMAIL_TEMPLATE,
        Permission.MASTER_ENTRY,
        Permission.FAQ_TYPE,
    ],
}


def seed_all(db: Session, admin_email: str, admin_password: str) -> None:
    PermissionRepository(db).sync_catalogue()
    logger.info("Permission catalogue synchronised.")

    seed_countries(db)
    seed_ethiopia_geography(db)
    seed_lookups(db)
    seed_product_categories(db)
    seed_email_templates(db)
    seed_content(db)
    seed_roles_and_admin(db, admin_email, admin_password)
    logger.info("Seeding complete.")


def seed_countries(db: Session) -> None:
    for payload in [data.ETHIOPIA, *data.OTHER_COUNTRIES]:
        code = payload["country_code"]
        if (
            db.execute(select(Country).where(Country.country_code == code))
            .scalars()
            .first()
        ):
            continue
        db.add(Country(**payload))
    db.commit()
    logger.info("Countries seeded.")


def seed_ethiopia_geography(db: Session) -> None:
    existing = (
        db.execute(
            select(AdminArea).where(
                AdminArea.country_code == "ET", AdminArea.level == 1
            )
        )
        .scalars()
        .first()
    )
    if existing:
        logger.info("Ethiopian geography already present; skipped.")
        return

    regions: dict[str, AdminArea] = {}
    for code, name, local_name in data.ETHIOPIA_REGIONS:
        region = AdminArea(
            country_code="ET",
            area_code=code,
            area_name=name,
            area_name_local=local_name,
            level=1,
            is_api_data_enabled=True,
        )
        db.add(region)
        regions[code] = region
    db.flush()

    for region in regions.values():
        region.path = str(region.area_id)

    for region_code, zones in data.ETHIOPIA_ZONES.items():
        parent = regions.get(region_code)
        if parent is None:
            continue
        for code, name, local_name in zones:
            db.add(
                AdminArea(
                    country_code="ET",
                    area_code=code,
                    area_name=name,
                    area_name_local=local_name,
                    level=2,
                    parent_id=parent.area_id,
                    path=f"{parent.path}.",
                )
            )
    db.flush()

    # Zone paths need the child id, which only exists after the flush above.
    for zone in db.execute(
        select(AdminArea).where(AdminArea.country_code == "ET", AdminArea.level == 2)
    ).scalars():
        zone.path = f"{zone.parent_id}.{zone.area_id}"

    db.commit()
    logger.info("Ethiopian regions and zones seeded.")


def seed_lookups(db: Session) -> None:
    for kind, entries in data.LOOKUP_SEEDS.items():
        if kind not in LOOKUPS:
            logger.warning("Unknown lookup kind '%s' in seed data; skipped.", kind)
            continue
        repo = LookupRepository(db, kind)
        for name, code in entries:
            if repo.name_taken(name):
                continue
            repo.create(name, code=code)

    seed_sub_categories(db)
    logger.info("Lookup tables seeded.")


def seed_sub_categories(db: Session) -> None:
    categories = {
        category.category_name: category
        for category in db.execute(select(Category)).scalars().all()
    }
    for category_name, names in data.SUB_CATEGORY_SEEDS.items():
        category = categories.get(category_name)
        if category is None:
            continue
        for name in names:
            exists = (
                db.execute(
                    select(SubCategory).where(
                        SubCategory.category_id == category.category_id,
                        SubCategory.sub_category_name == name,
                    )
                )
                .scalars()
                .first()
            )
            if not exists:
                db.add(
                    SubCategory(
                        sub_category_name=name, category_id=category.category_id
                    )
                )
    db.commit()


def seed_product_categories(db: Session) -> None:
    for order, (name, description) in enumerate(data.PRODUCT_CATEGORY_SEEDS, start=1):
        exists = (
            db.execute(
                select(ProductCategory).where(ProductCategory.category_name == name)
            )
            .scalars()
            .first()
        )
        if not exists:
            db.add(
                ProductCategory(
                    category_name=name, description=description, sort_order=order
                )
            )
    db.commit()
    logger.info("Product categories seeded.")


def seed_email_templates(db: Session) -> None:
    for order, (code, name, subject, body) in enumerate(
        data.EMAIL_TEMPLATE_SEEDS, start=1
    ):
        exists = (
            db.execute(
                select(EmailTemplate).where(
                    EmailTemplate.template_code == code, EmailTemplate.locale == "en"
                )
            )
            .scalars()
            .first()
        )
        if exists:
            continue
        db.add(
            EmailTemplate(
                template_code=code,
                template_name=name,
                subject=subject,
                body_text=body,
                variables=extract_placeholders(f"{subject} {body}"),
                sort_order=order,
            )
        )
    db.commit()
    logger.info("Email templates seeded.")


def seed_content(db: Session) -> None:
    _seed_faqs(db)
    _seed_terms(db)
    _seed_home_blocks(db)
    logger.info("CMS content seeded.")


def _seed_faqs(db: Session) -> None:
    for type_order, (type_name, questions) in enumerate(data.FAQ_SEEDS, start=1):
        faq_type = (
            db.execute(
                select(FaqType).where(
                    FaqType.faq_type == type_name, FaqType.locale == "en"
                )
            )
            .scalars()
            .first()
        )
        if faq_type is None:
            faq_type = FaqType(faq_type=type_name, sort_order=type_order)
            db.add(faq_type)
            db.flush()

        for order, (question, answer) in enumerate(questions, start=1):
            exists = (
                db.execute(
                    select(FaqDetail).where(
                        FaqDetail.type_id == faq_type.type_id,
                        FaqDetail.question == question,
                    )
                )
                .scalars()
                .first()
            )
            if not exists:
                db.add(
                    FaqDetail(
                        type_id=faq_type.type_id,
                        question=question,
                        answer=answer,
                        sort_order=order,
                    )
                )
    db.commit()


def _seed_terms(db: Session) -> None:
    for order, (title, content) in enumerate(data.TERMS_SEEDS, start=1):
        exists = (
            db.execute(
                select(TermCondition).where(TermCondition.sidebar_title == title)
            )
            .scalars()
            .first()
        )
        if not exists:
            db.add(
                TermCondition(
                    sidebar_title=title, term_content=content, sort_order=order
                )
            )
    db.commit()


def _seed_home_blocks(db: Session) -> None:
    for block in data.HOME_BLOCK_SEEDS:
        exists = (
            db.execute(
                select(HomePageBlock).where(
                    HomePageBlock.block_key == block["block_key"],
                    HomePageBlock.locale == "en",
                )
            )
            .scalars()
            .first()
        )
        if not exists:
            db.add(HomePageBlock(**block))
    db.commit()


def seed_roles_and_admin(db: Session, admin_email: str, admin_password: str) -> None:
    super_role = _ensure_role(db, SUPER_ROLE, editable=False)
    for role_name, grants in ROLE_GRANTS.items():
        role = _ensure_role(db, role_name)
        _grant(db, role, grants)

    # The super role is granted everything so the tree renders fully ticked.
    _grant(db, super_role, list(PERMISSION_TREE))

    existing = (
        db.execute(select(AdmUser).where(AdmUser.email_id == admin_email.lower()))
        .scalars()
        .first()
    )
    if existing:
        logger.info("Master administrator already exists; skipped.")
        return

    db.add(
        AdmUser(
            first_name="Network",
            last_name="Administrator",
            email_id=admin_email.lower(),
            login_name=admin_email.split("@")[0],
            login_pass=hash_password(admin_password),
            is_master=True,
            is_activated=True,
            role_id=super_role.role_id,
            country_code="ET",
        )
    )
    db.commit()
    logger.info("Master administrator created: %s", admin_email)


def _ensure_role(db: Session, role_name: str, editable: bool = True) -> AdmRole:
    role = (
        db.execute(select(AdmRole).where(AdmRole.role_name == role_name))
        .scalars()
        .first()
    )
    if role is None:
        role = AdmRole(role_name=role_name, is_editable=editable)
        db.add(role)
        db.commit()
        db.refresh(role)
    return role


def _grant(db: Session, role: AdmRole, permission_ids: list) -> None:
    existing = {
        row.permission_id
        for row in db.execute(
            select(AdmRolePermission).where(AdmRolePermission.role_id == role.role_id)
        )
        .scalars()
        .all()
    }
    for permission_id in permission_ids:
        if int(permission_id) not in existing:
            db.add(
                AdmRolePermission(
                    role_id=role.role_id,
                    permission_id=int(permission_id),
                    is_allowed=True,
                )
            )
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the OAN sandbox database.")
    parser.add_argument(
        "--admin-email",
        default=os.getenv("SEED_ADMIN_EMAIL", "admin@openagrinet.org"),
        help="Email address for the master administrator account.",
    )
    parser.add_argument(
        "--admin-password",
        default=os.getenv("SEED_ADMIN_PASSWORD", ""),
        help="Password for the master administrator. Prefer SEED_ADMIN_PASSWORD.",
    )
    args = parser.parse_args()

    if not args.admin_password:
        parser.error(
            "A master administrator password is required. Pass --admin-password or "
            "set SEED_ADMIN_PASSWORD."
        )

    db = SessionLocal()
    try:
        seed_all(db, args.admin_email, args.admin_password)
    except Exception:
        db.rollback()
        logger.exception("Seeding failed; no partial state was committed.")
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
