"""rename assignee_id to assigned_to

Revision ID: 053d80b23966
Revises: ae938c6cdb66
Create Date: 2024-03-19 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '053d80b23966'
down_revision: Union[str, None] = 'ae938c6cdb66'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the existing foreign key constraint
    op.drop_constraint('fk_tasks_assignee', 'tasks', type_='foreignkey')
    # Rename the column
    op.alter_column('tasks', 'assignee_id', new_column_name='assigned_to')
    # Recreate the foreign key constraint with the new column name
    op.create_foreign_key(
        'fk_tasks_assigned_to',
        'tasks', 'users',
        ['assigned_to'], ['id']
    )


def downgrade() -> None:
    # Drop the foreign key constraint
    op.drop_constraint('fk_tasks_assigned_to', 'tasks', type_='foreignkey')
    # Rename the column back
    op.alter_column('tasks', 'assigned_to', new_column_name='assignee_id')
    # Recreate the original foreign key constraint
    op.create_foreign_key(
        'fk_tasks_assignee',
        'tasks', 'users',
        ['assignee_id'], ['id']
    )
