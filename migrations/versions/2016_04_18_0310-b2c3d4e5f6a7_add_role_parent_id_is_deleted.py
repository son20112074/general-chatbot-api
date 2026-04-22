"""Add parent_id and is_deleted to roles table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-12

- parent_id: Integer, nullable, FK to roles.id with ON DELETE SET NULL
- is_deleted: Boolean, NOT NULL, server default false

After running upgrade(), run the backfill SQL to populate parent_id from
existing parent_path data (see end of this file for the SQL).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add parent_id column: nullable FK to roles.id, SET NULL on delete
    op.add_column(
        'roles',
        sa.Column('parent_id', sa.Integer(), nullable=True),
        schema='public',
    )
    op.create_foreign_key(
        'fk_roles_parent_id',
        'roles',
        'roles',
        ['parent_id'],
        ['id'],
        source_schema='public',
        referent_schema='public',
        ondelete='SET NULL',
    )

    # Add is_deleted column: NOT NULL, default false
    op.add_column(
        'roles',
        sa.Column(
            'is_deleted',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        schema='public',
    )

    # Backfill parent_id from parent_path.
    # parent_path format: ',1,5,' → direct parent is the last non-empty segment → 5
    # Empty string or NULL → parent_id stays NULL.
    op.execute(
        """
        UPDATE public.roles
        SET parent_id = (
            -- Split on comma, filter empty strings, take the last element, cast to int
            SELECT elem::integer
            FROM unnest(string_to_array(trim(both ',' from public.roles.parent_path), ','))
                 WITH ORDINALITY AS t(elem, ord)
            WHERE elem <> ''
            ORDER BY ord DESC
            LIMIT 1
        )
        WHERE parent_path IS NOT NULL AND parent_path <> ''
        """
    )


def downgrade() -> None:
    op.drop_constraint('fk_roles_parent_id', 'roles', schema='public', type_='foreignkey')
    op.drop_column('roles', 'parent_id', schema='public')
    op.drop_column('roles', 'is_deleted', schema='public')
