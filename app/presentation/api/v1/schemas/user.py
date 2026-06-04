from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


class UserBase(BaseModel):
    email: Optional[str] = Field(default=None, examples=[None])
    account_name: str = Field(..., max_length=50)
    full_name: str = Field(..., max_length=100)
    avatar: Optional[str] = Field(default=None, examples=[None])
    role_id: Optional[int] = Field(default=None, examples=[None], description="Role ID, null or int")


class UserCreate(BaseModel):
    account_name: str = Field(..., max_length=50, description="Required")
    full_name: str = Field(..., max_length=100, description="Required")
    password: str = Field(..., description="Required")
    role_id: int = Field(..., description="Required - role to assign")
    email: Optional[str] = Field(default=None, examples=[None])
    avatar: Optional[str] = Field(default=None, examples=[None])


class UserUpdate(BaseModel):
    email: Optional[str] = Field(default=None, examples=[None])
    account_name: Optional[str] = Field(default=None, examples=[None], max_length=50)
    full_name: Optional[str] = Field(default=None, examples=[None], max_length=100)
    password: Optional[str] = Field(default=None, examples=[None])
    avatar: Optional[str] = Field(default=None, examples=[None])
    role_id: Optional[int] = Field(default=None, examples=[None])


class UserResponse(BaseModel):
    id: int
    account_name: str
    email: Optional[str] = None
    full_name: str
    avatar: Optional[str] = None
    role_id: Optional[int] = None
    role_path: Optional[str] = None
    status: Optional[bool] = True
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class GetUsersQuery(BaseModel):
    ids: Optional[List[str]] = Field(default=None, examples=[None])
    fields: Optional[List[str]] = Field(default=None, examples=[None])
    condition: Optional[Dict] = Field(default=None, examples=[None])
    search_text: Optional[str] = Field(default=None, examples=[None])
    search_fields: Optional[List[str]] = Field(default=None, examples=[None])
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=1000)
