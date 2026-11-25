"""gateway route snapshot: the routes of the last pull, per gateway

Revision ID: h9c3d7e5f1a4
Revises: g8b2c6d4e0f3
Create Date: 2026-11-18

"Pull from gateway" (by hand or every GATEWAY_AUTO_PULL_HOURS) keeps a copy of
the gateway's routes; app sync resolves route ids from it instead of reading
the Admin API each time. Empty until the first pull, and app sync then reads
the gateway as before.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'h9c3d7e5f1a4'
down_revision: str | None = 'g8b2c6d4e0f3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'gateway_route_snapshot',
        sa.Column('environment', sa.String(length=16), primary_key=True),
        sa.Column('gateway_type', sa.String(length=16), nullable=False),
        sa.Column('routes', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column('pulled_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('pulled_by', sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('gateway_route_snapshot')
