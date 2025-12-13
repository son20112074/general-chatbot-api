from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    type: str = Field(..., description="Task type: 'recurring' or 'ad_hoc'")
    priority: str = Field(default='medium', description="Task priority: 'low', 'medium', 'high', 'critical'")
    status: str = Field(default='new', description="Task status: 'new', 'in_progress', 'pending_approval', 'completed', 'overdue', 'paused', 'cancelled'")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    progress: int = Field(default=0, ge=0, le=100)
    assigned_to: List[int] = Field(default_factory=list, description="List of user IDs assigned to this task")
    file_list: List[str] = Field(default_factory=list, description="List of file strings")
    file_name_list: List[str] = Field(default_factory=list, description="List of file name strings")
    parent_path: Optional[str] = None

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    assigned_to: Optional[List[int]] = None
    file_list: Optional[List[str]] = None
    file_name_list: Optional[List[str]] = None
    parent_path: Optional[str] = None

class TaskInDB(TaskBase):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class TaskResponse(TaskInDB):
    pass 