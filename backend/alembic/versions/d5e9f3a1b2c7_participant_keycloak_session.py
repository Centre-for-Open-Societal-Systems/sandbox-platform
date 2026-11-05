"""participant sessions: Keycloak session of a Keycloak sign-in

Revision ID: d5e9f3a1b2c7
Revises: c4d8e1f2a9b6
Create Date: 2026-11-04

With PARTICIPANT_AUTH_PROVIDER=keycloak the portal sign-in is checked by
Keycloak; ``participant_token.keycloak_sid`` ties the sandbox session
(x-auth-key) to the Keycloak session its access tokens carry (``sid``).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = 'd5e9f3a1b2c7'
down_revision: str | None = 'c4d8e1f2a9b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('participant_token', sa.Column('keycloak_sid', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_participant_token_keycloak_sid'), 'participant_token', ['keycloak_sid'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_participant_token_keycloak_sid'), table_name='participant_token')
    op.drop_column('participant_token', 'keycloak_sid')
