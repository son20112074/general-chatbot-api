"""
Utility functions for table lookup with schema support.
"""

from sqlalchemy import Table
from app.core.database import Base
from app.core.config import settings


def get_table_with_schema(table_name: str) -> Table:
    """
    Get a table from SQLAlchemy metadata with schema support.
    
    Args:
        table_name: Name of the table to lookup
        
    Returns:
        SQLAlchemy Table object
        
    Raises:
        ValueError: If table is not found
    """
    # Try to get table without schema prefix first
    table = Base.metadata.tables.get(table_name)
    
    # If not found, try with schema prefix
    if table is None:
        schema_table_name = f"{settings.DB_SCHEMA}.{table_name}"
        table = Base.metadata.tables.get(schema_table_name)
    
    if table is None:
        raise ValueError(f"Unknown table: {table_name}")
    
    return table
