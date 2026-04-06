"""update files table: add folder_id, role_id, type, is_deleted, node_path; widen hash

Revision ID: 0e4b94eef339
Revises: 100598117dfc
Create Date: 2025-04-01
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0e4b94eef339'
down_revision: Union[str, None] = '100598117dfc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Widen hash column
    op.alter_column('files', 'hash', type_=sa.String(128), existing_type=sa.String(64))

    # Add new columns (created_by stays as-is)
    op.add_column('files', sa.Column('folder_id', sa.Integer(),
                  sa.ForeignKey('folders.id', ondelete='SET NULL'), nullable=True))
    op.add_column('files', sa.Column('role_id', sa.Integer(),
                  sa.ForeignKey('roles.id', ondelete='SET NULL'), nullable=True))
    op.add_column('files', sa.Column('type', sa.String(15), server_default='private', nullable=False))
    op.add_column('files', sa.Column('node_path', sa.Text(), nullable=True))
    op.add_column('files', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=True))

    op.execute("ALTER TABLE files ADD CONSTRAINT ck_files_type CHECK (type IN ('private', 'organization', 'general'))")

    op.create_index('idx_files_folder_id', 'files', ['folder_id'])
    op.create_index('idx_files_role_id', 'files', ['role_id'])
    op.create_index('idx_files_type', 'files', ['type'])
    op.create_index('idx_files_node_path', 'files', ['node_path'])
    op.create_index('idx_files_is_deleted', 'files', ['is_deleted'])


def downgrade() -> None:
    op.drop_index('idx_files_is_deleted', 'files')
    op.drop_index('idx_files_node_path', 'files')
    op.drop_index('idx_files_type', 'files')
    op.drop_index('idx_files_role_id', 'files')
    op.drop_index('idx_files_folder_id', 'files')
    op.execute("ALTER TABLE files DROP CONSTRAINT IF EXISTS ck_files_type")
    op.drop_column('files', 'is_deleted')
    op.drop_column('files', 'node_path')
    op.drop_column('files', 'type')
    op.drop_column('files', 'role_id')
    op.drop_column('files', 'folder_id')
    op.alter_column('files', 'hash', type_=sa.String(64), existing_type=sa.String(128))
