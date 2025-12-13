from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict

class UserBase(BaseModel):
    email: Optional[str] = Field(default=None)
    account_name: str = Field(..., min_length=1, max_length=50)
    full_name: str = Field(..., min_length=1, max_length=100)
    avatar: Optional[str] = Field(default="")
    role_id: Optional[int] = Field(default=None)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

class UserUpdate(BaseModel):
    email: str | None = Field(None, min_length=1)
    account_name: str | None = Field(None, min_length=3, max_length=50)
    full_name: str | None = Field(None, min_length=1, max_length=100)
    password: str | None = Field(None, min_length=8)
    avatar: Optional[str] = None
    role_id: Optional[int] = None

class UserResponse(UserBase):
    id: int

    class Config:
        from_attributes = True

class GetUsersQuery(BaseModel):
    ids: List[str] = Field(default_factory=list)
    fields: List[str] = Field(default_factory=list)
    condition: Dict = Field(default_factory=dict)
    search_text: Optional[str] = None
    search_fields: List[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=1000)