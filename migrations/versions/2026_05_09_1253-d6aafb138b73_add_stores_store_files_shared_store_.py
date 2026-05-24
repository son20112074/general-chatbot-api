"""add stores store_files shared_store tables

Revision ID: d6aafb138b73
Revises: add_is_use_timeline
Create Date: 2026-05-09 12:53:37.774375

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6aafb138b73'
down_revision: Union[str, None] = 'add_is_use_timeline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create stores, shared_store, store_files."""
    op.create_table(
        'stores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['public.users.id']),
        sa.PrimaryKeyConstraint('id'),
        schema='public',
    )
    op.create_index(
        'idx_stores_name_owner_active', 'stores', ['name', 'created_by'],
        unique=True, schema='public',
        postgresql_where=sa.text('is_deleted = false'),
    )

    op.create_table(
        'shared_store',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['store_id'], ['public.stores.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['public.users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('store_id', 'user_id', name='uq_shared_store'),
        schema='public',
    )
    op.create_index('idx_shared_store_store_id', 'shared_store', ['store_id'], unique=False, schema='public')
    op.create_index('idx_shared_store_user_id', 'shared_store', ['user_id'], unique=False, schema='public')

    op.create_table(
        'store_files',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('file_id', sa.Integer(), nullable=False),
        sa.Column('store_id', sa.Integer(), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['file_id'], ['public.files.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['store_id'], ['public.stores.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_id', 'store_id', name='uq_store_file'),
        schema='public',
    )
    op.create_index('idx_store_files_file_id', 'store_files', ['file_id'], unique=False, schema='public')
    op.create_index('idx_store_files_store_id', 'store_files', ['store_id'], unique=False, schema='public')


def downgrade() -> None:
    """Downgrade schema: drop store_files, shared_store, stores."""
    op.drop_index('idx_store_files_store_id', table_name='store_files', schema='public')
    op.drop_index('idx_store_files_file_id', table_name='store_files', schema='public')
    op.drop_table('store_files', schema='public')

    op.drop_index('idx_shared_store_user_id', table_name='shared_store', schema='public')
    op.drop_index('idx_shared_store_store_id', table_name='shared_store', schema='public')
    op.drop_table('shared_store', schema='public')

    op.drop_index('idx_stores_name_owner_active', table_name='stores', schema='public', postgresql_where=sa.text('is_deleted = false'))
    op.drop_table('stores', schema='public')
