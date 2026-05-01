"""add storage node id to files

Revision ID: 008
Revises: 007
Create Date: 2026-05-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '008'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('files', sa.Column('storage_node_id', sa.String(100), nullable=True))
    op.create_index('idx_files_storage_node_id', 'files', ['storage_node_id'])


def downgrade() -> None:
    op.drop_index('idx_files_storage_node_id', table_name='files')
    op.drop_column('files', 'storage_node_id')
