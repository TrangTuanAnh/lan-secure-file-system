"""create audit_logs table

Revision ID: 007
Revises: 006
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '007'
down_revision: Union[str, None] = '006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column('actor_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(30), nullable=False),
        sa.Column('target_type', sa.String(20), nullable=False),
        sa.Column('target_id', sa.String(36), nullable=False),
        sa.Column('room_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('detail', postgresql.JSONB, nullable=True),
        sa.Column('status', sa.String(10), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'])
    )
    
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_logs_room_id', 'audit_logs', ['room_id'])
    op.create_index('idx_audit_logs_actor_id', 'audit_logs', ['actor_id'])


def downgrade() -> None:
    op.drop_index('idx_audit_logs_actor_id')
    op.drop_index('idx_audit_logs_room_id')
    op.drop_index('idx_audit_logs_created_at')
    op.drop_table('audit_logs')
