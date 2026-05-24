from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class EmployeeKPIBase(BaseModel):
    user_id: int = Field(..., description="ID của nhân viên")
    period_type: str = Field(..., description="Loại kỳ: daily, monthly, quarterly, yearly")
    period_value: str = Field(..., description="Giá trị của kỳ (VD: '2024-01', 'Q1-2024', '2024')")
    auto_kpi: Optional[float] = Field(None, description="KPI tự động")
    user_self_assessment: Optional[float] = Field(None, description="KPI user tự đánh giá")
    user_assessment_reason: Optional[str] = Field(None, description="Lý do user đánh giá")
    manager_assessment: Optional[float] = Field(None, description="KPI do cấp trên đánh giá")
    manager_assessment_reason: Optional[str] = Field(None, description="Lý do cấp trên đánh giá")
    assessed_by: Optional[int] = Field(None, description="ID người đánh giá")

class EmployeeKPICreate(EmployeeKPIBase):
    pass

class EmployeeKPIUpdate(BaseModel):
    auto_kpi: Optional[float] = Field(None, description="KPI tự động")
    user_self_assessment: Optional[float] = Field(None, description="KPI user tự đánh giá")
    user_assessment_reason: Optional[str] = Field(None, description="Lý do user đánh giá")
    user_assessment_time: Optional[datetime] = Field(None, description="Thời gian user đánh giá")
    manager_assessment: Optional[float] = Field(None, description="KPI do cấp trên đánh giá")
    manager_assessment_reason: Optional[str] = Field(None, description="Lý do cấp trên đánh giá")
    manager_assessment_time: Optional[datetime] = Field(None, description="Thời gian cấp trên đánh giá")
    assessed_by: Optional[int] = Field(None, description="ID người đánh giá")

class EmployeeKPIResponse(EmployeeKPIBase):
    id: int
    user_assessment_time: Optional[datetime] = None
    manager_assessment_time: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class EmployeeKPIFilter(BaseModel):
    user_id: Optional[int] = Field(None, description="Lọc theo ID nhân viên")
    period_type: Optional[str] = Field(None, description="Lọc theo loại kỳ")
    period_value: Optional[str] = Field(None, description="Lọc theo giá trị kỳ")
    assessed_by: Optional[int] = Field(None, description="Lọc theo người đánh giá")

# Schema cho thông tin user
class UserInfo(BaseModel):
    id: int
    full_name: str
    account_name: str
    email: Optional[str] = None
    avatar: Optional[str] = None

# Schema cho API tổng hợp KPI theo kỳ
class KPISummaryRequest(BaseModel):
    period_type: str = Field(..., description="Loại kỳ: daily, monthly, quarterly, yearly")
    from_time: datetime = Field(..., description="Thời gian bắt đầu")
    to_time: datetime = Field(..., description="Thời gian kết thúc")

# Schema cho API tự đánh giá KPI
class SelfAssessmentRequest(BaseModel):
    period_type: str = Field(..., description="Loại kỳ: daily, monthly, quarterly, yearly")
    period_value: str = Field(..., description="Giá trị của kỳ (VD: '2024-01', 'Q1-2024', '2024')")
    user_self_assessment: float = Field(..., ge=0, le=10, description="Điểm tự đánh giá (0-10)")
    user_assessment_reason: str = Field(..., description="Lý do tự đánh giá")

# Schema cho API quản lý đánh giá KPI
class ManagerAssessmentRequest(BaseModel):
    user_id: int = Field(..., description="ID nhân viên được đánh giá")
    period_type: str = Field(..., description="Loại kỳ: daily, monthly, quarterly, yearly")
    period_value: str = Field(..., description="Giá trị của kỳ (VD: '2024-01', 'Q1-2024', '2024')")
    manager_assessment: float = Field(..., ge=0, le=10, description="Điểm quản lý đánh giá (0-10)")
    manager_assessment_reason: str = Field(..., description="Lý do quản lý đánh giá")

class KPISummaryItem(BaseModel):
    period: str = Field(..., description="Tên kỳ (VD: '01/08/2025', 'Tháng 1 2025')")
    task_count: int = Field(..., description="Số lượng task được assign")
    work_count: int = Field(..., description="Số lượng task work được tạo")
    user_self_assessment: Optional[float] = Field(None, description="Tự đánh giá (VD: 9.8)")
    user_assessment_reason: Optional[str] = Field(None, description="Lý do tự đánh giá")
    manager_assessment: Optional[float] = Field(None, description="QL đánh giá (VD: 7.4)")
    manager_assessment_reason: Optional[str] = Field(None, description="Lý do QL đánh giá")
    manager_info: Optional[UserInfo] = Field(None, description="Thông tin người quản lý đánh giá")

class KPISummaryResponse(BaseModel):
    user_id: int
    period_type: str
    from_time: datetime
    to_time: datetime
    summary: List[KPISummaryItem] 

# Schema cho API lấy thông tin KPI theo role và role con
class RoleKPISummaryRequest(BaseModel):
    from_time: datetime = Field(..., description="Thời gian bắt đầu")
    to_time: datetime = Field(..., description="Thời gian kết thúc")
    period_type: str = Field(..., description="Loại kỳ: daily, monthly, quarterly, yearly")
    period_value: str = Field(..., description="Giá trị của kỳ (VD: '2024-01', 'Q1-2024', '2024')")

class RoleKPISummaryItem(BaseModel):
    user_id: int = Field(..., description="ID nhân viên")
    full_name: str = Field(..., description="Tên nhân viên")
    position: str = Field(..., description="Vị trí/Role")
    role_id: int = Field(..., description="ID của role")
    role_path: str = Field(..., description="Đường dẫn role")
    role_parent_path: str = Field(..., description="Parent path của role")
    user_avatar: Optional[str] = Field(None, description="Avatar của user")
    task_count: int = Field(..., description="Số lượng công việc")
    work_count: int = Field(..., description="Số lượng task work")
    user_self_assessment: Optional[float] = Field(None, description="Tự đánh giá")
    user_assessment_reason: Optional[str] = Field(None, description="Lý do tự đánh giá")
    manager_assessment: Optional[float] = Field(None, description="QL đánh giá")
    manager_assessment_reason: Optional[str] = Field(None, description="Lý do QL đánh giá")

class RoleKPISummaryResponse(BaseModel):
    from_time: datetime
    to_time: datetime
    summary: List[RoleKPISummaryItem] 