"""merge heads before file management

Revision ID: 59726e8560c7
Revises: 5f2fad5f973a, 2.7, 3be3c1da2c51
Create Date: 2025-04-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '59726e8560c7'
down_revision: Union[str, None] = ('5f2fad5f973a', '2.7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
