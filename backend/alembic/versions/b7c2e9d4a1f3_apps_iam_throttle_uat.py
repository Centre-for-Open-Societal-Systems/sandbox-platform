"""participant apps & API products, gateway logs, Keycloak users, auth throttle, UAT stage

Revision ID: b7c2e9d4a1f3
Revises: 1cfae55a0b79
Create Date: 2026-10-29

One migration for everything added after the initial schema:

* API products (access bundles of catalogue endpoints, with optional
  per-minute rate limit and per-day quota), participant apps (optional IP
  whitelist; name unique per participant + environment among apps that are
  not deleted), app <-> API product grants and the apps' API key / secret
  credentials. See ``app/models/app.py``.
* ``api_log``: ``source`` (TRYIT / DIRECT), ``app_id`` and the gateway's
  request id for calls APISIX reports through the logs callback, plus a
  (participant, timestamp) index for the usage reports.
* ``participant_iam_user``: each participant is one Keycloak user holding
  environment roles of a shared client (``ParticipantIamUser``).
* ``auth_throttle``: sign-in lockout, OTP attempts and per-IP limits on auth
  routes. Reset and invitation tokens are now stored as SHA-256 hashes;
  pending ones are hashed in place, so links already sent keep working.
* API Usage & Billing console screen (permission 31), granted to every role
  that can already open API History.
* Two promotion stages, UAT and production: the sandbox stage is folded into
  UAT. Signing up is now the UAT request; approving UAT opens the account. So
  that nobody loses access, everyone with sandbox access gets UAT access, a
  registration waiting for approval becomes a pending UAT request and a
  rejected one a UAT rejection; rows labelled SANDBOX become UAT; seeded
  portal texts that still hold the old wording are reworded.

This revision keeps the id of the last of the migrations it replaces
(``b7c2e9d4a1f3``), so a database already upgraded through them is at head
and needs nothing.
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.base import GUID, JSONB

revision: str = 'b7c2e9d4a1f3'
down_revision: str | None = '1cfae55a0b79'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PENDING, APPROVED, REJECTED = 0, 1, 2

AUDIT_LOGS = 14
API_HISTORY = 16
API_USAGE = 31

#: (table, column) holding one-time tokens that are stored hashed.
TOKEN_COLUMNS = (("participant", "reset_pass_token"), ("adm_user", "set_pass_token"))

OLD_WELCOME = (
    "<p>Dear {{name}},</p><p>Your email address is verified and your Open Agri "
    "Net account is active. Sandbox access is enabled straight away - sign in "
    "at {{portal_url}} to browse the API catalogue and start making calls.</p>"
    "<p>When you are ready to move beyond the sandbox, complete your "
    "organisation profile and request UAT access from your dashboard.</p>"
)
NEW_WELCOME = (
    "<p>Dear {{name}},</p><p>Your email address is verified and your Open Agri "
    "Net registration has been received. An administrator will review it for "
    "UAT access; we will email you once it is approved, and you can then sign "
    "in at {{portal_url}} to browse the API catalogue and start making calls.</p>"
    "<p>When you are ready to go live, complete your organisation profile and "
    "request production access from your dashboard.</p>"
)
OLD_PROMOTION = (
    "<p>Dear {{name}},</p><p>Your request for {{environment}} access has been "
    "approved.</p>"
)
NEW_PROMOTION = (
    "<p>Dear {{name}},</p><p>Your request for {{environment}} access has been "
    "approved. Sign in at {{portal_url}} to continue.</p>"
)

#: (old question, old answer, new question, new answer)
FAQS = [
    (
        "How long does approval take?",
        "Sandbox access is usually reviewed within three working days. UAT "
        "and production promotions take longer because they include a "
        "technical and compliance assessment.",
        "How long does approval take?",
        "UAT access is usually reviewed within three working days of "
        "registration. Production requests take longer because they include "
        "a technical and compliance assessment.",
    ),
    (
        "What data does the sandbox return?",
        "The sandbox serves synthetic data that matches the production "
        "schema exactly. No real farmer records are exposed at this stage.",
        "What data does UAT return?",
        "UAT serves synthetic data that matches the production schema "
        "exactly. No real farmer records are exposed at this stage.",
    ),
    (
        "Are there rate limits?",
        "Sandbox traffic is limited to 60 requests per minute per "
        "user. UAT and production limits are agreed during "
        "onboarding.",
        "Are there rate limits?",
        "UAT traffic is limited to 60 requests per minute per user. "
        "Production limits are agreed during onboarding.",
    ),
    (
        "How do I move from sandbox to production?",
        "Complete UAT certification first, then raise a production request "
        "from your dashboard with the required compliance documents.",
        "How do I move from UAT to production?",
        "Complete your organisation profile, then raise a production request "
        "from your dashboard with the required compliance documents.",
    ),
]

_STEP_4 = {"step": 4, "title": "Go live", "body": "Request production access and start serving real users."}
OLD_STEPS = {"steps": [
    {"step": 1, "title": "Register", "body": "Submit your organisation details and supporting documents."},
    {"step": 2, "title": "Explore the sandbox", "body": "Test against synthetic data with full API references."},
    {"step": 3, "title": "Certify in UAT", "body": "Validate your integration against pre-production services."},
    _STEP_4,
]}
NEW_STEPS = {"steps": [
    {"step": 1, "title": "Register",
     "body": "Sign up and verify your email address. An administrator reviews it for UAT access."},
    {"step": 2, "title": "Build in UAT",
     "body": "Test against synthetic data with full API references, apps and keys."},
    {"step": 3, "title": "Complete your profile",
     "body": "Submit your organisation details and supporting documents."},
    _STEP_4,
]}


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('added_by', sa.BigInteger(), nullable=True),
        sa.Column('modify_by', sa.BigInteger(), nullable=True),
        sa.Column('added_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('modify_date', sa.DateTime(timezone=True), nullable=True),
    ]


def _texts(welcome, promotion, faqs, steps, faq_type) -> None:
    """Each argument is (old, new); a row is changed only while it still holds old."""
    bind = op.get_bind()
    template = sa.text(
        "UPDATE email_template SET body_text = :new, template_name = :name "
        "WHERE template_code = :code AND body_text = :old"
    )
    (old_welcome, new_welcome, welcome_name) = welcome
    bind.execute(template, {"code": "PARTICIPANT_WELCOME", "old": old_welcome, "new": new_welcome,
                            "name": welcome_name})
    bind.execute(template, {"code": "PROMOTION_APPROVED", "old": promotion[0], "new": promotion[1],
                            "name": "Environment access approved"})
    old_steps, new_steps = steps
    old_type, new_type = faq_type
    for old_q, old_a, new_q, new_a in faqs:
        bind.execute(
            sa.text("UPDATE faq_detail SET question = :nq, answer = :na WHERE question = :oq AND answer = :oa"),
            {"oq": old_q, "oa": old_a, "nq": new_q, "na": new_a},
        )
    bind.execute(sa.text("UPDATE faq_type SET faq_type = :new WHERE faq_type = :old"),
                 {"old": old_type, "new": new_type})
    bind.execute(
        sa.text("UPDATE home_page_block SET content = CAST(:new AS jsonb) "
                "WHERE block_key = 'how_it_works' AND content = CAST(:old AS jsonb)"),
        {"old": json.dumps(old_steps), "new": json.dumps(new_steps)},
    )


def upgrade() -> None:
    # --- API products, participant apps, grants and credentials -------------
    op.create_table('api_product',
    sa.Column('api_product_id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('display_name', sa.String(length=250), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('approval_type', sa.String(length=10), nullable=False),
    sa.Column('is_published', sa.Boolean(), nullable=False),
    sa.Column('country_code', sa.String(length=2), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('unique_id', GUID(), nullable=False),
    *_audit_columns(),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('rate_limit_per_minute', sa.Integer(), nullable=True),
    sa.Column('quota_per_day', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('api_product_id', name=op.f('pk_api_product'))
    )
    op.create_index(op.f('ix_api_product_country_code'), 'api_product', ['country_code'], unique=False)
    op.create_index(op.f('ix_api_product_is_published'), 'api_product', ['is_published'], unique=False)
    op.create_index(op.f('ix_api_product_name'), 'api_product', ['name'], unique=False)
    op.create_index(op.f('ix_api_product_unique_id'), 'api_product', ['unique_id'], unique=True)

    op.create_table('participant_app',
    sa.Column('app_id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('participant_id', sa.BigInteger(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=1000), nullable=True),
    sa.Column('callback_url', sa.String(length=1000), nullable=True),
    sa.Column('environment', sa.String(length=20), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('revoked_reason', sa.Text(), nullable=True),
    sa.Column('gateway_consumer', sa.String(length=100), nullable=True),
    sa.Column('gateway_status', sa.String(length=10), nullable=False),
    sa.Column('gateway_error', sa.Text(), nullable=True),
    sa.Column('gateway_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('gateway_routes', JSONB, nullable=True),
    sa.Column('gateway_warnings', JSONB, nullable=True),
    sa.Column('unique_id', GUID(), nullable=False),
    *_audit_columns(),
    sa.Column('is_enabled', sa.Boolean(), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('allowed_ips', JSONB, nullable=True),
    sa.ForeignKeyConstraint(['participant_id'], ['participant.participant_id'], name=op.f('fk_participant_app_participant_id_participant')),
    sa.PrimaryKeyConstraint('app_id', name=op.f('pk_participant_app')),
    sa.UniqueConstraint('gateway_consumer', name=op.f('uq_participant_app_gateway_consumer')),
    )
    op.create_index(op.f('ix_participant_app_environment'), 'participant_app', ['environment'], unique=False)
    op.create_index(op.f('ix_participant_app_participant_id'), 'participant_app', ['participant_id'], unique=False)
    op.create_index(op.f('ix_participant_app_status'), 'participant_app', ['status'], unique=False)
    op.create_index(op.f('ix_participant_app_unique_id'), 'participant_app', ['unique_id'], unique=True)
    # Unique among apps that are not deleted, so a deleted app's name can be reused.
    op.create_index(
        'uq_participant_app_name',
        'participant_app',
        ['participant_id', 'name', 'environment'],
        unique=True,
        postgresql_where=sa.text('is_deleted = false'),
    )

    op.create_table('participant_app_credential',
    sa.Column('credential_id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('app_id', sa.BigInteger(), nullable=False),
    sa.Column('api_key_encrypted', sa.String(length=500), nullable=False),
    sa.Column('api_secret_encrypted', sa.String(length=500), nullable=False),
    sa.Column('api_key_hash', sa.String(length=64), nullable=False),
    sa.Column('api_key_prefix', sa.String(length=12), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('issued_date', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_used_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('unique_id', GUID(), nullable=False),
    *_audit_columns(),
    sa.ForeignKeyConstraint(['app_id'], ['participant_app.app_id'], name=op.f('fk_participant_app_credential_app_id_participant_app'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('credential_id', name=op.f('pk_participant_app_credential')),
    sa.UniqueConstraint('api_key_hash', name=op.f('uq_participant_app_credential_api_key_hash'))
    )
    op.create_index(op.f('ix_participant_app_credential_app_id'), 'participant_app_credential', ['app_id'], unique=False)
    op.create_index(op.f('ix_participant_app_credential_status'), 'participant_app_credential', ['status'], unique=False)
    op.create_index(op.f('ix_participant_app_credential_unique_id'), 'participant_app_credential', ['unique_id'], unique=True)

    op.create_table('participant_app_product',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('app_id', sa.BigInteger(), nullable=False),
    sa.Column('api_product_id', sa.BigInteger(), nullable=False),
    sa.Column('status', sa.Integer(), nullable=False),
    sa.Column('remarks', sa.Text(), nullable=True),
    sa.Column('decided_by', sa.BigInteger(), nullable=True),
    sa.Column('decided_date', sa.DateTime(timezone=True), nullable=True),
    *_audit_columns(),
    sa.ForeignKeyConstraint(['api_product_id'], ['api_product.api_product_id'], name=op.f('fk_participant_app_product_api_product_id_api_product')),
    sa.ForeignKeyConstraint(['app_id'], ['participant_app.app_id'], name=op.f('fk_participant_app_product_app_id_participant_app'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_participant_app_product')),
    sa.UniqueConstraint('app_id', 'api_product_id', name='uq_participant_app_product')
    )
    op.create_index(op.f('ix_participant_app_product_api_product_id'), 'participant_app_product', ['api_product_id'], unique=False)
    op.create_index(op.f('ix_participant_app_product_app_id'), 'participant_app_product', ['app_id'], unique=False)
    op.create_index(op.f('ix_participant_app_product_status'), 'participant_app_product', ['status'], unique=False)

    op.create_table('api_product_endpoint',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('api_product_id', sa.BigInteger(), nullable=False),
    sa.Column('endpoint_id', sa.BigInteger(), nullable=False),
    sa.Column('added_date', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['api_product_id'], ['api_product.api_product_id'], name=op.f('fk_api_product_endpoint_api_product_id_api_product'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['endpoint_id'], ['endpoint.endpoint_id'], name=op.f('fk_api_product_endpoint_endpoint_id_endpoint'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_api_product_endpoint')),
    sa.UniqueConstraint('api_product_id', 'endpoint_id', name='uq_api_product_endpoint')
    )
    op.create_index(op.f('ix_api_product_endpoint_api_product_id'), 'api_product_endpoint', ['api_product_id'], unique=False)
    op.create_index(op.f('ix_api_product_endpoint_endpoint_id'), 'api_product_endpoint', ['endpoint_id'], unique=False)

    # --- Gateway call logs ---------------------------------------------------
    op.add_column('api_log', sa.Column('source', sa.String(length=10), server_default='TRYIT', nullable=False))
    op.add_column('api_log', sa.Column('app_id', sa.BigInteger(), nullable=True))
    op.add_column('api_log', sa.Column('gateway_request_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_api_log_source'), 'api_log', ['source'], unique=False)
    op.create_index(op.f('ix_api_log_app_id'), 'api_log', ['app_id'], unique=False)
    op.create_unique_constraint('uq_api_log_gateway_request_id', 'api_log', ['gateway_request_id'])
    op.create_index(
        'ix_api_log_participant_timestamp', 'api_log', ['participant_id', 'log_timestamp'], unique=False
    )

    # --- Participant users in Keycloak --------------------------------------
    op.create_table('participant_iam_user',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('participant_id', sa.BigInteger(), nullable=False),
    sa.Column('realm', sa.String(length=100), nullable=False),
    sa.Column('username', sa.String(length=255), nullable=False),
    sa.Column('keycloak_id', sa.String(length=64), nullable=True),
    sa.Column('roles', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('password_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
    *_audit_columns(),
    sa.ForeignKeyConstraint(['participant_id'], ['participant.participant_id'], name=op.f('fk_participant_iam_user_participant_id_participant')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_participant_iam_user')),
    sa.UniqueConstraint('keycloak_id', name=op.f('uq_participant_iam_user_keycloak_id')),
    sa.UniqueConstraint('participant_id', name=op.f('uq_participant_iam_user_participant_id'))
    )
    op.create_index(op.f('ix_participant_iam_user_status'), 'participant_iam_user', ['status'], unique=False)

    # --- Auth throttle; one-time tokens stored hashed ------------------------
    op.create_table('auth_throttle',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=320), nullable=False),
    sa.Column('failures', sa.Integer(), nullable=False),
    sa.Column('window_start', sa.DateTime(timezone=True), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_auth_throttle')),
    )
    op.create_index(op.f('ix_auth_throttle_key'), 'auth_throttle', ['key'], unique=True)
    for table, column in TOKEN_COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = encode(sha256(convert_to({column}, 'UTF8')), 'hex') "
            f"WHERE {column} IS NOT NULL"
        )

    # --- API Usage & Billing console screen ----------------------------------
    op.execute(
        "INSERT INTO adm_permission (permission_id, menu_name, has_submenu, parent_id, sort_order) "
        f"SELECT {API_USAGE}, 'API Usage & Billing', false, {AUDIT_LOGS}, 31 "
        f"WHERE NOT EXISTS (SELECT 1 FROM adm_permission WHERE permission_id = {API_USAGE})"
    )
    op.execute(
        "INSERT INTO adm_role_permission (role_id, permission_id, is_allowed) "
        f"SELECT DISTINCT rp.role_id, {API_USAGE}, true FROM adm_role_permission rp "
        f"WHERE rp.permission_id = {API_HISTORY} AND rp.is_allowed "
        "AND NOT EXISTS (SELECT 1 FROM adm_role_permission x "
        f"WHERE x.role_id = rp.role_id AND x.permission_id = {API_USAGE})"
    )

    # --- Sandbox stage folded into UAT ---------------------------------------
    # Sandbox access -> UAT access.
    op.execute(
        "UPDATE participant SET is_uat_approved = true, is_uat_rejected = false, "
        "is_uat_requested = true, uat_approved_date = COALESCE(uat_approved_date, approved_date, now()) "
        "WHERE is_sandbox_approved AND NOT is_uat_approved"
    )
    # A UAT request still open for someone who now has UAT is granted.
    op.execute(
        f"UPDATE participant_request_info r SET status = {APPROVED}, reviewed_date = now(), "
        "remarks = COALESCE(r.remarks, 'Granted with sandbox access when the sandbox stage was retired') "
        "FROM participant p WHERE p.participant_id = r.participant_id AND p.is_uat_approved "
        f"AND r.target_environment IN ('UAT', 'SANDBOX') AND r.status = {PENDING}"
    )
    # Registrations waiting for approval -> UAT requests (with a pending request row).
    op.execute(
        "UPDATE participant SET is_uat_requested = true "
        f"WHERE is_approved = {PENDING} AND NOT is_rejected AND NOT is_uat_approved"
    )
    op.execute(
        "INSERT INTO participant_request_info "
        "(unique_id, participant_id, target_environment, status, remarks, added_by, added_date) "
        f"SELECT gen_random_uuid(), p.participant_id, 'UAT', {PENDING}, 'Sign-up', p.participant_id, now() "
        "FROM participant p "
        "WHERE p.is_uat_requested AND NOT p.is_uat_approved AND NOT p.is_uat_rejected "
        "AND NOT EXISTS (SELECT 1 FROM participant_request_info r WHERE r.participant_id = p.participant_id "
        f"AND r.target_environment = 'UAT' AND r.status = {PENDING})"
    )
    # Rejected registrations -> UAT rejections.
    op.execute("UPDATE participant SET is_uat_rejected = true WHERE is_rejected AND NOT is_uat_approved")
    # An account whose UAT was approved is an approved account.
    op.execute(
        f"UPDATE participant SET is_approved = {APPROVED} "
        f"WHERE is_uat_approved AND is_approved = {PENDING} AND NOT is_rejected"
    )
    op.execute("UPDATE api_log SET environment = 'UAT' WHERE environment = 'SANDBOX'")
    op.execute("UPDATE participant_request_info SET target_environment = 'UAT' WHERE target_environment = 'SANDBOX'")

    op.execute(
        "UPDATE endpoint SET uat_api_url = sandbox_api_url "
        "WHERE COALESCE(uat_api_url, '') = '' AND COALESCE(sandbox_api_url, '') <> ''"
    )
    op.drop_column('endpoint', 'sandbox_api_url')
    op.drop_column('participant', 'is_sandbox_approved')

    _texts((OLD_WELCOME, NEW_WELCOME, "Registration received"), (OLD_PROMOTION, NEW_PROMOTION),
           FAQS, (OLD_STEPS, NEW_STEPS), ("Using the Sandbox", "Using UAT"))


def downgrade() -> None:
    # --- Sandbox stage back ---------------------------------------------------
    op.add_column('participant', sa.Column('is_sandbox_approved', sa.Boolean(), nullable=True))
    op.execute("UPDATE participant SET is_sandbox_approved = is_uat_approved")
    op.alter_column('participant', 'is_sandbox_approved', nullable=False, server_default=sa.false())
    op.add_column('endpoint', sa.Column('sandbox_api_url', sa.String(length=2000), nullable=True))
    _texts((NEW_WELCOME, OLD_WELCOME, "Account activated"), (NEW_PROMOTION, OLD_PROMOTION),
           [(nq, na, oq, oa) for oq, oa, nq, na in FAQS], (NEW_STEPS, OLD_STEPS),
           ("Using UAT", "Using the Sandbox"))

    # --- API Usage & Billing console screen ----------------------------------
    op.execute(f"DELETE FROM adm_role_permission WHERE permission_id = {API_USAGE}")
    op.execute(f"DELETE FROM adm_permission WHERE permission_id = {API_USAGE}")

    # --- Auth throttle (hashed tokens cannot be restored; links sent stop working)
    op.drop_index(op.f('ix_auth_throttle_key'), table_name='auth_throttle')
    op.drop_table('auth_throttle')

    # --- Participant users in Keycloak --------------------------------------
    op.drop_index(op.f('ix_participant_iam_user_status'), table_name='participant_iam_user')
    op.drop_table('participant_iam_user')

    # --- Gateway call logs ---------------------------------------------------
    op.drop_index('ix_api_log_participant_timestamp', table_name='api_log')
    op.drop_constraint('uq_api_log_gateway_request_id', 'api_log', type_='unique')
    op.drop_index(op.f('ix_api_log_app_id'), table_name='api_log')
    op.drop_index(op.f('ix_api_log_source'), table_name='api_log')
    op.drop_column('api_log', 'gateway_request_id')
    op.drop_column('api_log', 'app_id')
    op.drop_column('api_log', 'source')

    # --- API products, participant apps, grants and credentials -------------
    op.drop_index(op.f('ix_api_product_endpoint_endpoint_id'), table_name='api_product_endpoint')
    op.drop_index(op.f('ix_api_product_endpoint_api_product_id'), table_name='api_product_endpoint')
    op.drop_table('api_product_endpoint')
    op.drop_index(op.f('ix_participant_app_product_status'), table_name='participant_app_product')
    op.drop_index(op.f('ix_participant_app_product_app_id'), table_name='participant_app_product')
    op.drop_index(op.f('ix_participant_app_product_api_product_id'), table_name='participant_app_product')
    op.drop_table('participant_app_product')
    op.drop_index(op.f('ix_participant_app_credential_unique_id'), table_name='participant_app_credential')
    op.drop_index(op.f('ix_participant_app_credential_status'), table_name='participant_app_credential')
    op.drop_index(op.f('ix_participant_app_credential_app_id'), table_name='participant_app_credential')
    op.drop_table('participant_app_credential')
    op.drop_index('uq_participant_app_name', table_name='participant_app')
    op.drop_index(op.f('ix_participant_app_unique_id'), table_name='participant_app')
    op.drop_index(op.f('ix_participant_app_status'), table_name='participant_app')
    op.drop_index(op.f('ix_participant_app_participant_id'), table_name='participant_app')
    op.drop_index(op.f('ix_participant_app_environment'), table_name='participant_app')
    op.drop_table('participant_app')
    op.drop_index(op.f('ix_api_product_unique_id'), table_name='api_product')
    op.drop_index(op.f('ix_api_product_name'), table_name='api_product')
    op.drop_index(op.f('ix_api_product_is_published'), table_name='api_product')
    op.drop_index(op.f('ix_api_product_country_code'), table_name='api_product')
    op.drop_table('api_product')
