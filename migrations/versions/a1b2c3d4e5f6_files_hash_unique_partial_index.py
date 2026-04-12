"""Replace files.hash unique constraint with partial unique index (exclude soft-deleted)

A soft-deleted file should not block re-uploading the same file.
The old constraint `files_hash_key` is a full UNIQUE on `hash`, which
prevents re-upload even when the original is soft-deleted (`is_deleted=true`).

This migration:
1. Drops the old UNIQUE constraint `files_hash_key`
2. Creates a partial unique index that only enforces uniqueness among
   non-deleted files: `CREATE UNIQUE INDEX ... WHERE is_deleted = false`

Revision ID: a1b2c3d4e5f6
Revises: 71b966ca9121
Create Date: 2026-04-12
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '71b966ca9121'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old full unique constraint on hash
    op.execute('ALTER TABLE files DROP CONSTRAINT IF EXISTS files_hash_key')
    # Create partial unique index: hash must be unique only among non-deleted files
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS files_hash_unique_active '
        'ON files (hash) WHERE is_deleted = false'
    )


def downgrade() -> None:
    # Drop the partial index
    op.execute('DROP INDEX IF EXISTS files_hash_unique_active')
    # Restore the old full unique constraint
    op.create_unique_constraint('files_hash_key', 'files', ['hash'])
