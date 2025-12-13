"""merge heads

Revision ID: eff6d276b83c
Revises: 4dc70aeb3cef, 9a1b2c3d4e5f
Create Date: 2025-07-06 00:54:54.792698

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eff6d276b83c'
down_revision: Union[str, None] = ('4dc70aeb3cef', '9a1b2c3d4e5f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
