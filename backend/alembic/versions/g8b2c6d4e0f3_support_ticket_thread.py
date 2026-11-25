"""support tickets: a conversation of messages per ticket

Revision ID: g8b2c6d4e0f3
Revises: f7a1b5c3d9e2
Create Date: 2026-11-12

A ticket used to hold one description and one reply. Messages now live in
``participant_query_message``; every existing ticket is converted (its
description becomes the first message, its reply the second), so nothing is
lost. ``participant_query.description`` / ``response`` stay as they were.
Downgrade drops the table and the new columns.
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = 'g8b2c6d4e0f3'
down_revision: str | None = 'f7a1b5c3d9e2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column('participant_query', sa.Column('awaiting_since', _TS, nullable=True))
    op.add_column('participant_query', sa.Column('last_message_date', _TS, nullable=True))
    op.add_column('participant_query', sa.Column('last_message_by', sa.String(length=12), nullable=True))
    op.add_column('participant_query', sa.Column('participant_read_date', _TS, nullable=True))
    op.add_column('participant_query', sa.Column('admin_read_date', _TS, nullable=True))
    op.add_column('participant_query', sa.Column('closed_date', _TS, nullable=True))
    op.create_index('ix_participant_query_last_message_date', 'participant_query', ['last_message_date'])

    op.create_table(
        'participant_query_message',
        sa.Column('message_id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('unique_id', sa.Uuid(), nullable=False),
        sa.Column(
            'query_id', sa.BigInteger(),
            sa.ForeignKey('participant_query.query_id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('author_type', sa.String(length=12), nullable=False),
        sa.Column('author_id', sa.BigInteger(), nullable=True),
        sa.Column('author_name', sa.String(length=200), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('is_internal', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('channel', sa.String(length=16), nullable=False, server_default='portal'),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('notified_date', _TS, nullable=True),
        sa.Column('added_date', _TS, nullable=True),
        sa.Column('modify_date', _TS, nullable=True),
    )
    op.create_index('ix_participant_query_message_unique_id', 'participant_query_message', ['unique_id'], unique=True)
    op.create_index('ix_participant_query_message_query_id', 'participant_query_message', ['query_id'])
    op.create_index('ix_participant_query_message_external_id', 'participant_query_message', ['external_id'])

    _convert_existing_tickets()


def _convert_existing_tickets() -> None:
    bind = op.get_bind()
    query = sa.table(
        'participant_query',
        sa.column('query_id'), sa.column('description'), sa.column('response'), sa.column('status'),
        sa.column('added_date'), sa.column('participant_id'),
        sa.column('responded_by'), sa.column('responded_date'), sa.column('last_message_date'),
        sa.column('last_message_by'), sa.column('participant_read_date'), sa.column('admin_read_date'),
        sa.column('closed_date'),
    )
    message = sa.table(
        'participant_query_message',
        sa.column('unique_id'), sa.column('query_id'), sa.column('author_type'), sa.column('author_id'),
        sa.column('body'), sa.column('is_internal'), sa.column('channel'), sa.column('added_date'),
        sa.column('modify_date'),
    )
    now = datetime.now(UTC)
    for row in bind.execute(sa.select(query)).mappings().all():
        opened = row['added_date'] or now
        last_at, last_by = opened, 'participant'
        bind.execute(message.insert().values(
            unique_id=uuid.uuid4(), query_id=row['query_id'], author_type='participant',
            author_id=row['participant_id'], body=row['description'] or '', is_internal=False,
            channel='portal', added_date=opened, modify_date=opened,
        ))
        if row['response']:
            replied = row['responded_date'] or opened
            bind.execute(message.insert().values(
                unique_id=uuid.uuid4(), query_id=row['query_id'], author_type='admin',
                author_id=row['responded_by'], body=row['response'], is_internal=False,
                channel='portal', added_date=replied, modify_date=replied,
            ))
            last_at, last_by = replied, 'admin'
        values = {
            'last_message_date': last_at, 'last_message_by': last_by,
            # Already-seen history: nothing shows as unread after the upgrade.
            'participant_read_date': now, 'admin_read_date': now,
        }
        if row['status'] == 3:
            values['closed_date'] = last_at
        bind.execute(query.update().where(query.c.query_id == row['query_id']).values(**values))


def downgrade() -> None:
    op.drop_table('participant_query_message')
    op.drop_index('ix_participant_query_last_message_date', table_name='participant_query')
    for column in (
        'closed_date', 'admin_read_date', 'participant_read_date',
        'last_message_by', 'last_message_date', 'awaiting_since',
    ):
        op.drop_column('participant_query', column)
