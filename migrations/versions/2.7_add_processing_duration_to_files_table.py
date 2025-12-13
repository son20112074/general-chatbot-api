"""Add processing_duration to files table

Revision ID: 2.7_add_processing_duration_to_files_table
Revises: 2.6_add_file_classification_columns
Create Date: 2025-01-27 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '2.7'
down_revision = '2.6_add_file_classification_columns'
branch_labels = None
depends_on = None


def upgrade():
    """Add processing_duration column to files table"""
    # Add processing_duration column to track processing time in seconds
    op.add_column('files', sa.Column('processing_duration', sa.Integer(), nullable=True))


def downgrade():
    """Remove processing_duration column from files table"""
    op.drop_column('files', 'processing_duration')
