from pydantic import BaseModel, Field
from typing import Optional, List, Dict

class UserBase(BaseModel):
    email: Optional[str] = Field(default=None, examples=[None])
    account_name: str = Field(..., max_length=50)
    full_name: str = Field(..., max_length=100)
    avatar: Optional[str] = Field(default=None, examples=[None])
    role_id: Optional[int] = Field(default=None, examples=[None], description="Role ID, null or int")

class UserCreate(UserBase):
    password: str = Field(...)

class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, examples=[None])
    account_name: Optional[str] = Field(default=None, examples=[None], max_length=50)
    full_name: Optional[str] = Field(default=None, examples=[None], max_length=100)
    password: Optional[str] = Field(default=None, examples=[None])
    avatar: Optional[str] = Field(default=None, examples=[None])
    role_id: Optional[int] = Field(default=None, examples=[None], description="Role ID, null or int")

class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True

class GetUsersQuery(BaseModel):
    ids: Optional[List[str]] = Field(default=None, examples=[None])
    fields: Optional[List[str]] = Field(default=None, examples=[None])
    condition: Optional[Dict] = Field(default=None, examples=[None])
    search_text: Optional[str] = Field(default=None, examples=[None])
    search_fields: Optional[List[str]] = Field(default=None, examples=[None])
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=1000)
