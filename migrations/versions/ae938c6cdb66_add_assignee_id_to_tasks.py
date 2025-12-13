"""add assignee_id to tasks

Revision ID: ae938c6cdb66
Revises: acdf7558aa74
Create Date: 2024-03-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae938c6cdb66'
down_revision: Union[str, None] = 'acdf7558aa74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add assignee_id column
    op.add_column('tasks', sa.Column('assignee_id', sa.Integer(), nullable=True))
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_tasks_assignee',
        'tasks', 'users',
        ['assignee_id'], ['id']
    )


def downgrade() -> None:
    # Remove foreign key constraint
    op.drop_constraint('fk_tasks_assignee', 'tasks', type_='foreignkey')
    # Remove assignee_id column
    op.drop_column('tasks', 'assignee_id')
