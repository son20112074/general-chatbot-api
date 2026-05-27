"""add system_settings table

Revision ID: 8b5ec65d10f1
Revises: 2d9e997eac59
Create Date: 2026-05-28 03:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.config import settings


# revision identifiers, used by Alembic.
revision: str = "8b5ec65d10f1"
down_revision: Union[str, None] = "2d9e997eac59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            [f"{settings.DB_SCHEMA}.users.id"],
            name="system_settings_created_by_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
        schema=settings.DB_SCHEMA,
    )
    op.create_index(
        "ix_system_settings_key",
        "system_settings",
        ["key"],
        unique=False,
        schema=settings.DB_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_system_settings_key",
        table_name="system_settings",
        schema=settings.DB_SCHEMA,
    )
    op.drop_table("system_settings", schema=settings.DB_SCHEMA)
