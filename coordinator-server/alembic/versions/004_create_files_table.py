"""create files table

Revision ID: 004
Revises: 003
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'files',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('room_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('original_name', sa.String(255), nullable=False),
        sa.Column('stored_name', sa.String(255), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('uploader_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('size_bytes', sa.BigInteger, nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('sha256_whole', sa.CHAR(64), nullable=False),
        sa.Column('total_chunks', sa.Integer, nullable=False),
        sa.Column('chunk_size', sa.Integer, nullable=False),
        sa.Column('status', sa.String(15), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploader_id'], ['users.id'])
    )
    
    op.create_index('idx_files_room_id', 'files', ['room_id'])
    op.create_index('idx_files_sha256_whole', 'files', ['sha256_whole'])
    op.create_index('idx_files_room_original', 'files', ['room_id', 'original_name'])


def downgrade() -> None:
    op.drop_index('idx_files_room_original')
    op.drop_index('idx_files_sha256_whole')
    op.drop_index('idx_files_room_id')
    op.drop_table('files')
