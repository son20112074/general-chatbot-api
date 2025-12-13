"""create personal_task_status table

Revision ID: 9a1b2c3d4e5f
Revises: 8d0430d2029f
Create Date: 2024-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, None] = '8d0430d2029f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'personal_task_status',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('task_id', sa.Integer(), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='new'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("status IN ('new', 'in_progress', 'completed')", name='check_personal_task_status'),
    )

def downgrade() -> None:
    op.drop_table('personal_task_status') 