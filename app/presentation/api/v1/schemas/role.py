from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None


class RoleCreate(BaseModel):
    name: str = Field(..., description="Name of the role (required)")
    description: Optional[str] = Field(default=None, examples=[None])
    parent_id: Optional[int] = Field(default=None, examples=[None], description="Parent role ID, null for root role")


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(default=None, examples=[None])
    description: Optional[str] = Field(default=None, examples=[None])
    parent_id: Optional[int] = Field(default=None, examples=[None], description="New parent role ID. Only allowed if role has no active users.")


class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    parent_path: Optional[str] = None
    level: int
    is_deleted: bool = False
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class RoleQuery(BaseModel):
    ids: Optional[List[int]] = Field(default=None, examples=[None])
    fields: Optional[List[str]] = Field(default=None, examples=[None])
    condition: Optional[Dict[str, Any]] = Field(default=None, examples=[None])
    search_text: Optional[str] = Field(default=None, examples=[None])
    search_fields: Optional[List[str]] = Field(default=None, examples=[None])
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class DeleteRoleSchema(BaseModel):
    id: Optional[int] = Field(default=None, examples=[None])
