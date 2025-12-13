from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.domain.services.auth_service import AuthService
from app.presentation.api.v1.schemas.auth import (
    LoginRequest, 
    LoginResponse, 
    RefreshTokenRequest,
    TokenResponse,
    TokenData,
    UserInfoResponse
)
from app.presentation.api.dependencies import get_current_user
from app.domain.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
async def login(
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    result = await auth_service.login(login_data.account_name, login_data.password)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return result

@router.get("/me", response_model=UserInfoResponse)
async def get_me(
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_service = UserService(db)
    user = await user_service.get_user(current_user.user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "user_id": user.id,
        "account_name": user.account_name,
        "full_name": user.full_name,
        "role_id": user.role_id,
        "avatar": user.avatar,
        "email": user.email,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None
    }

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    result = await auth_service.refresh_token(refresh_data.refresh_token)
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return result 