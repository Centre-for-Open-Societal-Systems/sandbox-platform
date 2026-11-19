"""participant_app.gateway_scopes: the OAuth scopes an app's tokens carry

Revision ID: i0d4e8f6a2b5
Revises: h9c3d7e5f1a4
Create Date: 2026-11-18

With GATEWAY_SCOPES the partner gateway checks the token's ``scope`` claim (the
scopes of the app's approved API products) instead of route ids. Empty until
an app is next synced (``scripts/keycloak/resync_apps.py`` syncs them all).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'i0d4e8f6a2b5'
down_revision: str | None = 'h9c3d7e5f1a4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'participant_app',
        sa.Column('gateway_scopes', postgresql.JSONB(), nullable=True, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column('participant_app', 'gateway_scopes')
