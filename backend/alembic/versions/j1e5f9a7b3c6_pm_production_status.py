"""participant_iam_user.pm_prod_*: the partner in production's own Partner Management

Revision ID: j1e5f9a7b3c6
Revises: i0d4e8f6a2b5
Create Date: 2026-11-18

Production runs its own PM (PM_PROD_*). A participant is onboarded there when
production access is approved and disabled there when it goes; these columns
hold that partner's state (ACTIVE / DISABLED / PENDING / FAILED), like pm_status
does for the UAT PM. PENDING: waiting for PM's own staff (PM_PROD_AUTO_APPROVE off).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'j1e5f9a7b3c6'
down_revision: str | None = 'i0d4e8f6a2b5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('participant_iam_user', sa.Column('pm_prod_status', sa.String(length=10), nullable=True))
    op.add_column('participant_iam_user', sa.Column('pm_prod_error', sa.Text(), nullable=True))
    op.add_column('participant_iam_user', sa.Column('pm_prod_synced_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('participant_iam_user', 'pm_prod_synced_at')
    op.drop_column('participant_iam_user', 'pm_prod_error')
    op.drop_column('participant_iam_user', 'pm_prod_status')
