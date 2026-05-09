"""add is_use_timeline to report_templates

Revision ID: add_is_use_timeline
Revises: 70cf5d2214da
Create Date: 2026-05-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'add_is_use_timeline'
down_revision: Union[str, None] = '70cf5d2214da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'report_templates',
        sa.Column('is_use_timeline', sa.Boolean(), nullable=False, server_default='false'),
        schema='public',
    )


def downgrade() -> None:
    op.drop_column('report_templates', 'is_use_timeline', schema='public')
