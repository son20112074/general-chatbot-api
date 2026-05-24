from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class TaskWorkBase(BaseModel):
    title: str = Field(..., description="Tiêu đề work")
    description: Optional[str] = Field(None, description="Mô tả work")
    content: Optional[str] = Field(None, description="Nội dung work")
    image_links: Optional[List[str]] = Field(default=[], description="Danh sách link hình ảnh")
    file_links: Optional[List[str]] = Field(default=[], description="Danh sách link file")
    attributes: Optional[dict] = Field(default={}, description="Thuộc tính bổ sung")
    is_difficult: Optional[bool] = Field(default=False, description="Đánh dấu khó khăn")
    task_id: Optional[int] = Field(None, description="ID của task")
    created_by: int = Field(..., description="ID người tạo")

class TaskWorkCreate(BaseModel):
    title: str = Field(..., description="Tiêu đề work")
    description: Optional[str] = Field(None, description="Mô tả work")
    content: Optional[str] = Field(None, description="Nội dung work")
    image_links: Optional[List[str]] = Field(default=[], description="Danh sách link hình ảnh")
    file_links: Optional[List[str]] = Field(default=[], description="Danh sách link file")
    attributes: Optional[dict] = Field(default={}, description="Thuộc tính bổ sung")
    is_difficult: Optional[bool] = Field(default=False, description="Đánh dấu khó khăn")
    task_id: Optional[int] = Field(None, description="ID của task")

class TaskWorkUpdate(BaseModel):
    title: Optional[str] = Field(None, description="Tiêu đề work")
    description: Optional[str] = Field(None, description="Mô tả work")
    content: Optional[str] = Field(None, description="Nội dung work")
    image_links: Optional[List[str]] = Field(None, description="Danh sách link hình ảnh")
    file_links: Optional[List[str]] = Field(None, description="Danh sách link file")
    attributes: Optional[dict] = Field(None, description="Thuộc tính bổ sung")
    is_difficult: Optional[bool] = Field(None, description="Đánh dấu khó khăn")
    task_id: Optional[int] = Field(None, description="ID của task")
    # Không bao gồm created_by vì không nên thay đổi người tạo khi update

class TaskWorkResponse(TaskWorkBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class TaskWorkFilter(BaseModel):
    user_id: int = Field(..., description="ID người dùng")
    from_time: datetime = Field(..., description="Thời gian bắt đầu")
    to_time: datetime = Field(..., description="Thời gian kết thúc")

class TaskWorkListResponse(BaseModel):
    user_id: int
    from_time: datetime
    to_time: datetime
    total_count: int
    works: List[TaskWorkResponse] 