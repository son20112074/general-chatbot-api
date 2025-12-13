"""Convert assigned_to to JSON array

Revision ID: 6cd796aebbf9
Revises: 3be3c1da2c51
Create Date: 2025-06-21 13:20:36.861398

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6cd796aebbf9'
down_revision: Union[str, None] = '3be3c1da2c51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # First, add a temporary column
    op.add_column('tasks', sa.Column('assigned_to_new', postgresql.JSON(), nullable=True))
    
    # Convert existing integer values to JSON arrays
    # For non-null values, convert to [value], for null values, use []
    op.execute("""
        UPDATE tasks 
        SET assigned_to_new = CASE 
            WHEN assigned_to IS NOT NULL THEN json_build_array(assigned_to)
            ELSE '[]'::json
        END
    """)
    
    # Drop the foreign key constraint first
    op.drop_constraint(op.f('fk_tasks_assigned_to'), 'tasks', type_='foreignkey')
    
    # Drop the old column
    op.drop_column('tasks', 'assigned_to')
    
    # Rename the new column to the original name
    op.alter_column('tasks', 'assigned_to_new', new_column_name='assigned_to')


def downgrade() -> None:
    """Downgrade schema."""
    # Add a temporary integer column
    op.add_column('tasks', sa.Column('assigned_to_old', sa.Integer(), nullable=True))
    
    # Convert JSON arrays back to integers
    # Take the first element of the array, or null if array is empty
    op.execute("""
        UPDATE tasks 
        SET assigned_to_old = CASE 
            WHEN assigned_to IS NOT NULL AND json_array_length(assigned_to) > 0 
            THEN (assigned_to->0)::int
            ELSE NULL
        END
    """)
    
    # Drop the JSON column
    op.drop_column('tasks', 'assigned_to')
    
    # Rename the old column back to the original name
    op.alter_column('tasks', 'assigned_to_old', new_column_name='assigned_to')
    
    # Recreate the foreign key constraint
    op.create_foreign_key(op.f('fk_tasks_assigned_to'), 'tasks', 'users', ['assigned_to'], ['id'])
