from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
# from app.domain.interfaces.home_repository import HomeRepository
from app.domain.services.auth_service import AuthService
from app.presentation.api.v1.schemas.auth import TokenData

from app.core.config import settings
from app.infrastructure.repositories.cache_repository import CacheRepositoryInterface
# from app.infrastructure.repositories.home_repository import SQLAlchemyHomeRepository
from app.infrastructure.repositories.raw_repository import RawDBRepository
from app.core.query import CommonQuery
from app.domain.services.task_service import TaskService

security = HTTPBearer()

# def get_auth_service() -> AuthService:
#     return AuthService()

def get_settings() -> dict:
    return {
        "redis_url": settings.REDIS_URL,
        "redis_port": settings.REDIS_PORT,
    }


def get_cache_repository() -> CacheRepositoryInterface:
    from app.infrastructure.repositories.cache_repository import RedisCacheRepository
    return RedisCacheRepository()

def get_raw_db_repository(db: AsyncSession = Depends(get_db)) -> RawDBRepository:
    """Get an instance of RawDBRepository using the existing database session"""
    return RawDBRepository(db)

def get_common_query(db: AsyncSession = Depends(get_db)) -> CommonQuery:
    """Get an instance of CommonQuery using the existing database session"""
    return CommonQuery(db)

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> TokenData:
    auth_service = AuthService(db)

    token_data = await auth_service.verify_token(credentials.credentials)
    
    if not token_data or token_data.token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return token_data

async def get_task_service(session: AsyncSession = Depends(get_db)) -> TaskService:
    """Get task service instance"""
    return TaskService(session)