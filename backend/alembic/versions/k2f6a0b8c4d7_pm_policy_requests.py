"""API products ask for Partner Management policies; the requests the sandbox files

Revision ID: k2f6a0b8c4d7
Revises: j1e5f9a7b3c6
Create Date: 2026-11-18

``api_product.pm_policy``: the OpenG2P PM access policy (PolicyInput) an API
product asks for. ``participant_pm_policy``: per participant, PM (UAT /
PRODUCTION) and policy key, what the sandbox filed and where it stands
(WAITING / PENDING / ACTIVE / REJECTED / REVOKING / FAILED), and where it was filed
(``backend``: pm = Partner Management policy requests, cm = COSS Consent Manager bindings).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'k2f6a0b8c4d7'
down_revision: str | None = 'j1e5f9a7b3c6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('api_product', sa.Column('pm_policy', postgresql.JSONB(), nullable=True))
    op.create_table(
        'participant_pm_policy',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('participant_id', sa.BigInteger(),
                  sa.ForeignKey('participant.participant_id', ondelete='CASCADE'), nullable=False),
        sa.Column('environment', sa.String(length=16), nullable=False),
        sa.Column('backend', sa.String(length=8), nullable=False, server_default='pm'),
        sa.Column('policy_key', sa.String(length=300), nullable=False),
        sa.Column('policy', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('products', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('participant_id', 'environment', 'backend', 'policy_key', name='uq_participant_pm_policy'),
    )
    op.create_index('ix_participant_pm_policy_participant_id', 'participant_pm_policy', ['participant_id'])
    op.create_index('ix_participant_pm_policy_status', 'participant_pm_policy', ['status'])


def downgrade() -> None:
    op.drop_index('ix_participant_pm_policy_status', 'participant_pm_policy')
    op.drop_index('ix_participant_pm_policy_participant_id', 'participant_pm_policy')
    op.drop_table('participant_pm_policy')
    op.drop_column('api_product', 'pm_policy')
