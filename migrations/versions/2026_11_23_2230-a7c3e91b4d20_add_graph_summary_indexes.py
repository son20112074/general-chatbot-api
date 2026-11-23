"""add indexes for graph summary and structure filters

Revision ID: a7c3e91b4d20
Revises: c8a1f4e29b37
Create Date: 2026-11-23 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op

from app.core.config import settings


revision: str = "a7c3e91b4d20"
down_revision: Union[str, None] = "c8a1f4e29b37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    schema = settings.DB_SCHEMA
    op.create_index(
        "ix_nodes_entity_type_created_at",
        "nodes",
        ["entity_type", "created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_nodes_created_at",
        "nodes",
        ["created_at"],
        schema=schema,
    )
    op.create_index(
        "ix_edges_edge_type",
        "edges",
        ["edge_type"],
        schema=schema,
    )


def downgrade() -> None:
    schema = settings.DB_SCHEMA
    op.drop_index("ix_edges_edge_type", table_name="edges", schema=schema)
    op.drop_index("ix_nodes_created_at", table_name="nodes", schema=schema)
    op.drop_index(
        "ix_nodes_entity_type_created_at", table_name="nodes", schema=schema
    )
