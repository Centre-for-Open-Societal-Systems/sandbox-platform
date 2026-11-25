"""participant users: Consent Manager partner portal and Partner Management

Revision ID: c4d8e1f2a9b6
Revises: b7c2e9d4a1f3
Create Date: 2026-11-03

``participant_iam_user`` records what the sandbox set up for the OpenG2P
Consent Manager partner portal: the participant's partner ID (Keycloak
attribute ``partner_id``), whether the user holds the portal role, and the
participant's partner in OpenG2P Partner Management (id, status, last error).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'c4d8e1f2a9b6'
down_revision: str | None = 'b7c2e9d4a1f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = 'participant_iam_user'


def upgrade() -> None:
    op.add_column(TABLE, sa.Column('partner_id', sa.String(length=100), nullable=True))
    op.add_column(TABLE, sa.Column('portal_access', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(TABLE, sa.Column('pm_partner_id', sa.String(length=255), nullable=True))
    op.add_column(TABLE, sa.Column('pm_status', sa.String(length=10), nullable=True))
    op.add_column(TABLE, sa.Column('pm_error', sa.Text(), nullable=True))
    op.add_column(TABLE, sa.Column('pm_synced_at', sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint(op.f('uq_participant_iam_user_partner_id'), TABLE, ['partner_id'])


def downgrade() -> None:
    op.drop_constraint(op.f('uq_participant_iam_user_partner_id'), TABLE, type_='unique')
    for column in ('pm_synced_at', 'pm_error', 'pm_status', 'pm_partner_id', 'portal_access', 'partner_id'):
        op.drop_column(TABLE, column)
