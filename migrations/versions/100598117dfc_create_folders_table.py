"""create folders table

Revision ID: 100598117dfc
Revises: 59726e8560c7
Create Date: 2025-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '100598117dfc'
down_revision: Union[str, None] = '59726e8560c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'folders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('parent_id', sa.Integer(), sa.ForeignKey('folders.id', ondelete='CASCADE'), nullable=True),
        sa.Column('parent_path', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('role_id', sa.Integer(), sa.ForeignKey('roles.id', ondelete='SET NULL'), nullable=True),
        sa.Column('type', sa.String(15), nullable=False, server_default='private'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('parent_id', 'name', 'created_by', name='uq_folders_parent_name_owner'),
        sa.CheckConstraint("type IN ('private', 'organization', 'general')", name='ck_folders_type'),
    )

    op.create_index('idx_folders_parent_id', 'folders', ['parent_id'])
    op.create_index('idx_folders_parent_path', 'folders', ['parent_path'])
    op.create_index('idx_folders_created_by', 'folders', ['created_by'])
    op.create_index('idx_folders_role_id', 'folders', ['role_id'])
    op.create_index('idx_folders_type', 'folders', ['type'])
    op.create_index('idx_folders_is_deleted', 'folders', ['is_deleted'])


def downgrade() -> None:
    op.drop_table('folders')
