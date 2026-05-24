from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    account_name: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class LoginResponse(TokenResponse):
    user_id: int
    account_name: str
    full_name: str
    role_id: int

class UserInfoResponse(BaseModel):
    user_id: int
    account_name: str
    full_name: str
    role_id: int
    avatar: Optional[str] = None
    email: Optional[str] = None
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None

class RefreshTokenRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class TokenData(BaseModel):
    user_id: Optional[int] = None
    account_name: Optional[str] = None
    role_id: Optional[int] = None
    token_type: Optional[str] = None 