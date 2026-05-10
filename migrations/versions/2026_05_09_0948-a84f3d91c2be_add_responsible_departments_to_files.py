"""add responsible_departments to files

Revision ID: a84f3d91c2be
Revises: 70cf5d2214da
Create Date: 2026-05-09 09:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a84f3d91c2be'
down_revision: Union[str, None] = '70cf5d2214da'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('files', sa.Column('responsible_departments', sa.ARRAY(sa.String()), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('files', 'responsible_departments')
