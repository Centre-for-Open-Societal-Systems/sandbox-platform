"""app keys: expiry, show-once secret, expiry notice

Revision ID: e6f0a4b2c3d8
Revises: d5e9f3a1b2c7
Create Date: 2026-11-12

``expires_date``: a key stops working then (lifetime at issue, or the grace
period of a rotated key). ``secret_viewed_date``: the secret is shown in clear
once. ``expiry_notified_date``: the "expires soon" email was sent.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'e6f0a4b2c3d8'
down_revision: str | None = 'd5e9f3a1b2c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('participant_app_credential', sa.Column('expires_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('participant_app_credential', sa.Column('secret_viewed_date', sa.DateTime(timezone=True), nullable=True))
    op.add_column('participant_app_credential', sa.Column('expiry_notified_date', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_participant_app_credential_expires_date'), 'participant_app_credential', ['expires_date'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_participant_app_credential_expires_date'), table_name='participant_app_credential')
    op.drop_column('participant_app_credential', 'expiry_notified_date')
    op.drop_column('participant_app_credential', 'secret_viewed_date')
    op.drop_column('participant_app_credential', 'expires_date')
