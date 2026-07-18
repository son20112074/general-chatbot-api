from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


DEFAULT_LINKED_SYSTEM_ICON = "appstore"

ALLOWED_LINKED_SYSTEM_ICONS = frozenset(
    {
        "bar-chart",
        "audit",
        "project",
        "sound",
        "message",
        "history",
        "translation",
        "file-text",
        "comment",
        "dashboard",
        "partition",
        "api",
        "link",
        "cloud-server",
        "database",
        "team",
        "setting",
        "folder",
        "book",
        "mail",
        "notification",
        "appstore",
    }
)


class LinkedSystemCreate(BaseModel):
    abbr: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    icon: str = Field(default=DEFAULT_LINKED_SYSTEM_ICON, max_length=64)
    url: str = Field(..., min_length=1)
    sort_order: int = Field(default=0)


class LinkedSystemUpdate(BaseModel):
    abbr: Optional[str] = Field(default=None, min_length=1, max_length=32)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    icon: Optional[str] = Field(default=None, max_length=64)
    url: Optional[str] = Field(default=None, min_length=1)
    sort_order: Optional[int] = Field(default=None)


class LinkedSystemResponse(BaseModel):
    id: int
    abbr: str
    name: str
    description: Optional[str] = None
    icon: str
    url: str
    sort_order: int
    is_deleted: bool = False
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


def normalize_icon(icon: Optional[str]) -> str:
    if not icon:
        return DEFAULT_LINKED_SYSTEM_ICON
    key = icon.strip()
    if key in ALLOWED_LINKED_SYSTEM_ICONS:
        return key
    return DEFAULT_LINKED_SYSTEM_ICON
