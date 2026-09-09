from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RoleStatisticItem(BaseModel):
    role_id: int = Field(..., description="ID của vai trò")
    role_name: str = Field(..., description="Tên vai trò")
    level: int = Field(..., description="Cấp của vai trò trong cây tổ chức")
    user_count: int = Field(..., description="Số người dùng đang hoạt động thuộc vai trò")
    file_count: int = Field(..., description="Số lượng file do vai trò tạo trong khoảng thời gian")
    question_count: int = Field(..., description="Số câu hỏi trong lịch sử chat của vai trò trong khoảng thời gian")


class RoleStatisticsResponse(BaseModel):
    from_time: Optional[datetime] = Field(None, description="Thời gian bắt đầu")
    to_time: Optional[datetime] = Field(None, description="Thời gian kết thúc")
    total_files: int = Field(..., description="Tổng số lượng file")
    total_questions: int = Field(..., description="Tổng số câu hỏi")
    statistics: List[RoleStatisticItem] = Field(..., description="Thống kê chi tiết theo vai trò")
