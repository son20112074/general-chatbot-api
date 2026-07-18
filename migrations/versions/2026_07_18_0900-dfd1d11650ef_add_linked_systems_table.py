"""add linked_systems table

Revision ID: dfd1d11650ef
Revises: dfd1d11650ee
Create Date: 2026-07-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.core.config import settings


revision: str = "dfd1d11650ef"
down_revision: Union[str, None] = "dfd1d11650ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    schema = settings.DB_SCHEMA
    op.create_table(
        "linked_systems",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("abbr", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            [f"{schema}.users.id"],
            name="linked_systems_created_by_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
        schema=schema,
    )
    op.create_index(
        "idx_linked_systems_abbr_active",
        "linked_systems",
        ["abbr"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("is_deleted = false"),
    )

    op.execute(
        sa.text(
            f"""
            INSERT INTO {schema}.linked_systems
                (abbr, name, description, icon, url, sort_order, is_deleted, created_at, updated_at)
            VALUES
                ('BCT', 'HT Báo cáo Tuần', 'Tổng hợp & quản lý báo cáo định kỳ',
                 'bar-chart', 'http://192.168.1.91:8003', 0, false, NOW(), NOW()),
                ('CMS', 'Quản lý Hồ sơ HĐ', 'Quản lý hồ sơ & hợp đồng tập trung',
                 'audit', 'http://192.168.1.91:8001', 1, false, NOW(), NOW()),
                ('TMS', 'Quản lý Công việc', 'Theo dõi & phân công nhiệm vụ nhóm',
                 'project', 'http://192.168.1.91:8002', 2, false, NOW(), NOW()),
                ('TTS', 'Văn bản → Tiếng nói', 'Chuyển đổi nội dung thành âm thanh',
                 'sound', 'http://192.168.1.91:8800/tts/', 3, false, NOW(), NOW())
            """
        )
    )


def downgrade() -> None:
    schema = settings.DB_SCHEMA
    op.drop_index(
        "idx_linked_systems_abbr_active",
        table_name="linked_systems",
        schema=schema,
    )
    op.drop_table("linked_systems", schema=schema)
