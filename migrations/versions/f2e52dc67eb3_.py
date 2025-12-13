"""empty message

Revision ID: f2e52dc67eb3
Revises: 8d0430d2029f
Create Date: 2025-06-21 13:57:20.777791

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f2e52dc67eb3'
down_revision: Union[str, None] = '8d0430d2029f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
        # 1. Thêm cột tạm
    op.add_column('tasks', sa.Column('assigned_to_tmp', postgresql.ARRAY(sa.Integer()), nullable=True))

    # 2. Copy dữ liệu từ assigned_to (JSONB) sang assigned_to_tmp (INTEGER[])
    op.execute("""
        UPDATE tasks
        SET assigned_to_tmp = (
            CASE
                WHEN assigned_to IS NULL THEN NULL
                ELSE (
                    SELECT array_agg((elem)::int)
                    FROM jsonb_array_elements_text(assigned_to) AS elem
                )
            END
        )
    """)

    # 3. Xoá cột cũ
    op.drop_column('tasks', 'assigned_to')

    # 4. Đổi tên cột mới
    op.alter_column('tasks', 'assigned_to_tmp', new_column_name='assigned_to')


def downgrade():
    # 1. Thêm lại cột JSONB
    op.add_column('tasks', sa.Column('assigned_to_tmp', postgresql.JSONB(), nullable=True))

    # 2. Copy dữ liệu từ integer[] sang JSONB
    op.execute("""
        UPDATE tasks
        SET assigned_to_tmp = to_jsonb(assigned_to)
    """)

    # 3. Xoá cột mảng int
    op.drop_column('tasks', 'assigned_to')

    # 4. Đổi tên cột JSONB lại thành cũ
    op.alter_column('tasks', 'assigned_to_tmp', new_column_name='assigned_to')
