"""create scan_reports table

Revision ID: 006
Revises: 005
Create Date: 2025-01-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006'
down_revision: Union[str, None] = '005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'scan_reports',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('file_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tool', sa.String(50), nullable=False),
        sa.Column('tool_version', sa.String(20), nullable=False),
        sa.Column('scanned_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('result', sa.String(10), nullable=False),
        sa.Column('file_sha256', sa.CHAR(64), nullable=False),
        sa.ForeignKeyConstraint(['file_id'], ['files.id'], ondelete='CASCADE')
    )
    
    op.create_index('idx_scan_reports_file_id', 'scan_reports', ['file_id'])


def downgrade() -> None:
    op.drop_index('idx_scan_reports_file_id')
    op.drop_table('scan_reports')
