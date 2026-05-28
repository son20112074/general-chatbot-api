"""add responsible_departments_reasons to files

Revision ID: 8b5ec65d10f2
Revises: 8b5ec65d10f1
Create Date: 2026-05-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b5ec65d10f2"
down_revision: Union[str, None] = "8b5ec65d10f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "files",
        sa.Column("responsible_departments_reasons", sa.ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("files", "responsible_departments_reasons")
