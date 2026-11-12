"""apps: drop the unused callback_url

Revision ID: f7a1b5c3d9e2
Revises: e6f0a4b2c3d8
Create Date: 2026-11-12

``participant_app.callback_url`` was stored and shown but nothing ever called it:
the registry APIs name the receiver in each request, and the sandbox sends no
webhooks. Downgrade restores the column (empty).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'f7a1b5c3d9e2'
down_revision: str | None = 'e6f0a4b2c3d8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column('participant_app', 'callback_url')


def downgrade() -> None:
    op.add_column('participant_app', sa.Column('callback_url', sa.String(length=1000), nullable=True))
