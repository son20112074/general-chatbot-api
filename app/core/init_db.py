import asyncio
from app.core.database import engine, Base

async def create_tables():
    """
    Create database tables using SQLAlchemy models
    """
    async with engine.begin() as conn:
        # Drop all tables if they exist (for dev only, remove in production)
        # await conn.run_sync(Base.metadata.drop_all)
        
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    
    print("Database tables created")

if __name__ == "__main__":
    asyncio.run(create_tables())