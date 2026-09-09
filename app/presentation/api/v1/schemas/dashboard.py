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


class UserStatisticItem(BaseModel):
    user_id: int = Field(..., description="ID của người dùng")
    account_name: str = Field(..., description="Tên đăng nhập")
    full_name: Optional[str] = Field(None, description="Tên đầy đủ")
    role_id: Optional[int] = Field(None, description="ID vai trò của người dùng")
    role_name: Optional[str] = Field(None, description="Tên vai trò của người dùng")
    file_count: int = Field(..., description="Số lượng file do người dùng tạo trong khoảng thời gian")
    question_count: int = Field(..., description="Số câu hỏi của người dùng trong khoảng thời gian")


class UserStatisticsResponse(BaseModel):
    from_time: Optional[datetime] = Field(None, description="Thời gian bắt đầu")
    to_time: Optional[datetime] = Field(None, description="Thời gian kết thúc")
    total_files: int = Field(..., description="Tổng số lượng file")
    total_questions: int = Field(..., description="Tổng số câu hỏi")
    statistics: List[UserStatisticItem] = Field(..., description="Thống kê chi tiết theo người dùng")
