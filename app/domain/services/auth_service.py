from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
import bcrypt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.domain.models.user import User
from app.core.config import settings
from app.presentation.api.v1.schemas.auth import TokenData

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        

    async def authenticate_user(self, account_name: str, password: str) -> Optional[User]:
        query = select(User).where(User.account_name == account_name)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return None
        if not self.verify_password(password, user.password):
            return None
        return user

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    def create_tokens(self, data: dict, access_expires_delta: Optional[timedelta] = None, 
                     refresh_expires_delta: Optional[timedelta] = None) -> Tuple[str, str]:
        to_encode = data.copy()
        
        # Create access token
        if access_expires_delta:
            access_expire = datetime.utcnow() + access_expires_delta
        else:
            access_expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        access_encode = to_encode.copy()
        access_encode.update({"exp": access_expire, "token_type": "access"})
        access_token = jwt.encode(access_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        # Create refresh token
        if refresh_expires_delta:
            refresh_expire = datetime.utcnow() + refresh_expires_delta
        else:
            refresh_expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        refresh_encode = to_encode.copy()
        refresh_encode.update({"exp": refresh_expire, "token_type": "refresh"})
        refresh_token = jwt.encode(refresh_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

        return access_token, refresh_token

    async def verify_token(self, token: str) -> Optional[TokenData]:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_id: int = int(payload.get("sub"))
            account_name: str = payload.get("account_name")
            role_id: int = int(payload.get("role_id"))
            token_type: str = payload.get("token_type")
            
            if user_id is None or account_name is None or token_type is None:
                return None
                
            return TokenData(user_id=user_id, account_name=account_name, role_id=role_id, token_type=token_type)
        except JWTError:
            return None

    async def login(self, account_name: str, password: str) -> Optional[dict]:
        # access_token, new_refresh_token = self.create_tokens(
        #         data={"sub": "3", "account_name": "admin2", "role_id": 1},
        #         access_expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        #         refresh_expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        #     )
            
        # print(access_token)

        user = await self.authenticate_user(account_name, password)
        if not user:
            return None

        # Update last login time
        user.last_login_at = datetime.utcnow()
        await self.db.commit()

        # Create tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        access_token, refresh_token = self.create_tokens(
            data={
                "sub": str(user.id), 
                "account_name": user.account_name,
                "role_id": user.role_id
            },
            access_expires_delta=access_token_expires,
            refresh_expires_delta=refresh_token_expires
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "account_name": user.account_name,
            "full_name": user.full_name,
            "role_id": user.role_id
        }
        

    async def refresh_token(self, refresh_token: str) -> Optional[dict]:
        token_data = await self.verify_token(refresh_token)
        if not token_data or token_data.token_type != "refresh":
            return None

        # Get user from database
        query = select(User).where(User.id == token_data.user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return None

        # Create new tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        refresh_token_expires = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        access_token, new_refresh_token = self.create_tokens(
            data={"sub": str(user.id), "account_name": user.account_name, "role_id": user.role_id},
            access_expires_delta=access_token_expires,
            refresh_expires_delta=refresh_token_expires
        )

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "user_id": user.id,
            "account_name": user.account_name,
            "full_name": user.full_name,
            "role_id": user.role_id
        } 
    
    
    
    
    

    