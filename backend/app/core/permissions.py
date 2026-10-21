"""Admin menu permissions.

Each console screen has a stable numeric id. A role is granted a set of ids in
``adm_role_permission``; the login response ships the resolved list so the
frontend can hide menu entries it may not open. Ids are append-only - never
renumber one, or existing role grants silently point at a different screen.
Names may change; the numbers must not.

Region/zone/woreda naming stays generic (``admin level 1/2/3``) because OAN is
multi-country: Ethiopia maps level 1 to Region, but a future member country
maps it to whatever its own hierarchy calls that tier.
"""

from __future__ import annotations

from enum import IntEnum


class Permission(IntEnum):
    ADMIN_USER_MANAGEMENT = 1
    AUM_VIEW_USER_LIST = 2
    AUM_ADD_NEW_USER = 3
    AUM_MANAGE_ROLES = 4

    API_CATALOGUE = 5

    PARTICIPANT_MANAGEMENT = 6
    ALL_PARTICIPANTS = 7
    UAT_PARTICIPANTS = 8
    UAT_APPROVAL_PENDING = 9
    UAT_REJECTED_PARTICIPANTS = 10
    PROD_PARTICIPANTS = 11
    PROD_APPROVAL_PENDING = 12
    PROD_REJECTED_PARTICIPANTS = 13

    AUDIT_LOGS = 14
    USER_TRACKING = 15
    API_HISTORY = 16

    MASTER_ENTRY = 17
    CATEGORY = 18
    MAPPER = 19
    MANAGE_GEOGRAPHY = 20
    FAQ_TYPE = 21
    USER_QUERIES = 22

    CMS = 23
    FAQS = 24
    TERMS_AND_CONDITIONS = 25
    EMAIL_TEMPLATE = 26

    # OAN additions beyond the reference console.
    COUNTRY_MANAGEMENT = 27
    NETWORK_PARTICIPANTS = 28


#: ``permission_id -> (label, parent_id, has_submenu)``. Seeded into
#: ``adm_permission`` and served to the frontend for sidebar rendering.
PERMISSION_TREE: dict[int, tuple[str, int | None, bool]] = {
    Permission.ADMIN_USER_MANAGEMENT: ("Admin User Management", None, True),
    Permission.AUM_VIEW_USER_LIST: (
        "View User List",
        Permission.ADMIN_USER_MANAGEMENT,
        False,
    ),
    Permission.AUM_ADD_NEW_USER: (
        "Add New User",
        Permission.ADMIN_USER_MANAGEMENT,
        False,
    ),
    Permission.AUM_MANAGE_ROLES: (
        "Manage Roles",
        Permission.ADMIN_USER_MANAGEMENT,
        False,
    ),
    Permission.API_CATALOGUE: ("API Catalogue", None, False),
    Permission.PARTICIPANT_MANAGEMENT: ("Participant Management", None, True),
    Permission.ALL_PARTICIPANTS: (
        "All Participants",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.UAT_PARTICIPANTS: (
        "UAT Participants",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.UAT_APPROVAL_PENDING: (
        "UAT Approval Pending",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.UAT_REJECTED_PARTICIPANTS: (
        "UAT Rejected",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.PROD_PARTICIPANTS: (
        "Production Participants",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.PROD_APPROVAL_PENDING: (
        "Production Approval Pending",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.PROD_REJECTED_PARTICIPANTS: (
        "Production Rejected",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
    Permission.AUDIT_LOGS: ("Audit Logs", None, True),
    Permission.USER_TRACKING: ("User Tracking", Permission.AUDIT_LOGS, False),
    Permission.API_HISTORY: ("API History", Permission.AUDIT_LOGS, False),
    Permission.MASTER_ENTRY: ("Master Entry", None, True),
    Permission.CATEGORY: ("Categories", Permission.MASTER_ENTRY, False),
    Permission.MAPPER: ("Mapper", Permission.MASTER_ENTRY, False),
    Permission.MANAGE_GEOGRAPHY: ("Manage Geography", Permission.MASTER_ENTRY, False),
    Permission.FAQ_TYPE: ("FAQ Types", Permission.MASTER_ENTRY, False),
    Permission.USER_QUERIES: ("User Queries", Permission.MASTER_ENTRY, False),
    Permission.CMS: ("Content", None, True),
    Permission.FAQS: ("FAQs", Permission.CMS, False),
    Permission.TERMS_AND_CONDITIONS: ("Terms & Conditions", Permission.CMS, False),
    Permission.EMAIL_TEMPLATE: ("Email Templates", Permission.CMS, False),
    Permission.COUNTRY_MANAGEMENT: (
        "Country Management",
        Permission.MASTER_ENTRY,
        False,
    ),
    Permission.NETWORK_PARTICIPANTS: (
        "Network Members",
        Permission.PARTICIPANT_MANAGEMENT,
        False,
    ),
}


def all_permission_ids() -> list[int]:
    return [int(p) for p in PERMISSION_TREE]
