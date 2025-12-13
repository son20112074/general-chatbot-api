from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine
from app.core.config import settings
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# Create async engine - convert PostgresDsn to string
engine: AsyncEngine = create_async_engine(
    str(settings.DATABASE_URI),  # Convert to string here
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW
)

# Create sessionmaker with async session
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

Base = declarative_base()

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions"""
    session = AsyncSessionLocal()
    try:
        yield session
    finally:
        await session.close()

# Update the get_db dependency to use the context manager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_db_session() as session:
        yield session