"""Add classification columns to files table

Revision ID: 2.6_add_file_classification_columns
Revises: 1.9
Create Date: 2025-01-27 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2.6'
down_revision = '1.9'
branch_labels = None
depends_on = None


def upgrade():
    """Add classification columns to files table"""
    # Add new array columns for file classification
    op.add_column('files', sa.Column('listed_nation', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('files', sa.Column('important_news', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('files', sa.Column('listed_technology', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('files', sa.Column('listed_company', postgresql.ARRAY(sa.String()), nullable=True))


def downgrade():
    """Remove classification columns from files table"""
    op.drop_column('files', 'listed_company')
    op.drop_column('files', 'listed_technology')
    op.drop_column('files', 'important_news')
    op.drop_column('files', 'listed_nation')
