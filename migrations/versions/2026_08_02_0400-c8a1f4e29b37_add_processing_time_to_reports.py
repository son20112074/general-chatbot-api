"""add processing_time to reports

Revision ID: c8a1f4e29b37
Revises: dfd1d11650ef
Create Date: 2026-08-02 04:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.config import settings


revision: str = "c8a1f4e29b37"
down_revision: Union[str, None] = "dfd1d11650ef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "reports",
        sa.Column("processing_time", sa.Float(), nullable=True),
        schema=settings.DB_SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("reports", "processing_time", schema=settings.DB_SCHEMA)
