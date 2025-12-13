from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class RoleBase(BaseModel):
    name: str
    level: int
    description: Optional[str] = None

class RoleCreate(BaseModel):
    name: str = Field(..., description="Name of the role")
    description: Optional[str] = Field(..., description="Description of the role")
    parent_path: str = Field(..., description="Parent path in the role hierarchy")

class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, description="Name of the role")
    description: Optional[str] = Field(None, description="Description of the role")
    parent_path: Optional[str] = Field(None, description="Parent path in the role hierarchy")

class RoleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    parent_path: Optional[str] = None
    level: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }

class RoleQuery(BaseModel):
    ids: Optional[List[int]] = None
    fields: Optional[List[str]] = None
    condition: Optional[Dict[str, Any]] = None
    search_text: Optional[str] = None
    search_fields: Optional[List[str]] = None
    page: int = 1
    page_size: int = 10

class DeleteRoleSchema(BaseModel):
    parent_path: str = Field(..., description="Parent path of the role to delete")
    id: int = Field(..., description="ID of the role to delete") 