"""create share_tokens table

Revision ID: 005
Revises: 004
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'share_tokens',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('token', sa.CHAR(64), nullable=False, unique=True),
        sa.Column('file_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('created_by', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('max_downloads', sa.Integer, nullable=False),
        sa.Column('download_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'])
    )
    
    op.create_index('idx_share_tokens_token', 'share_tokens', ['token'], unique=True)
    op.create_index('idx_share_tokens_file_id', 'share_tokens', ['file_id'])


def downgrade() -> None:
    op.drop_index('idx_share_tokens_file_id')
    op.drop_index('idx_share_tokens_token')
    op.drop_table('share_tokens')
