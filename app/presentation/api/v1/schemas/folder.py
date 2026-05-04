from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class FolderType(str, Enum):
    private = "private"
    organization = "organization"
    general = "general"


class FolderCreate(BaseModel):
    name: str = Field(..., max_length=255, description="Folder name")
    parent_id: Optional[int] = Field(default=None, examples=[None], description="Parent folder ID, null = root, int = parent folder id")
    type: FolderType = Field(default=FolderType.private, description="Folder type")
    description: Optional[str] = Field(default=None, examples=[None], description="Folder description")


class FolderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, examples=[None], max_length=255, description="Folder name")
    description: Optional[str] = Field(default=None, examples=[None], description="Folder description")


class FolderMove(BaseModel):
    new_parent_id: Optional[int] = Field(default=None, examples=[None], description="New parent folder ID, null = move to root, int = target folder id")


class FolderResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None
    parent_path: Optional[str] = None
    created_by: int
    role_id: Optional[int] = None
    type: str
    description: Optional[str] = None
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class TreeNodeResponse(BaseModel):
    """A node in the file manager tree. Can be a role, folder, or file.
    When depth > 1, children are populated recursively."""
    node_type: str
    id: int
    name: str
    has_children: bool = False
    children: Optional[List[TreeNodeResponse]] = None
    owner: Optional[Dict[str, Any]] = None
    # folder-specific
    parent_id: Optional[int] = None
    created_by: Optional[int] = None
    type: Optional[str] = None
    description: Optional[str] = None
    # file-specific
    size: Optional[int] = None
    hash: Optional[str] = None
    path: Optional[str] = None
    extension: Optional[str] = None
    mime_type: Optional[str] = None
    node_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_processed: Optional[bool] = None
    processing_duration: Optional[int] = None
    # role-specific
    level: Optional[int] = None
    parent_path: Optional[str] = None


class FolderQuery(BaseModel):
    parent_id: Optional[int] = Field(default=None, examples=[None], description="Filter by parent folder ID")
    type: Optional[FolderType] = Field(default=None, examples=[None], description="Filter by type")
    search_text: Optional[str] = Field(default=None, examples=[None], description="Search by name or description")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
