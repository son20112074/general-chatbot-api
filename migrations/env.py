import os
import sys
import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add the parent directory to the path so we can import app models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # Import settings
from app.core.database import Base  # Import Base
from app.domain.models import *  # Import models

# this is the Alembic Config object
config = context.config

# Set the SQLAlchemy URL - convert from asyncpg to regular postgres for alembic
async_url = str(settings.DATABASE_URI)
sync_url = async_url.replace('postgresql+asyncpg://', 'postgresql://')
config.set_main_option("sqlalchemy.url", sync_url)
# Interpret the config file for Python logging
fileConfig(config.config_file_name)

# Set up target metadata
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Using the synchronous engine for migrations
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()