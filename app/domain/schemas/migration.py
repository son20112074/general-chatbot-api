from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field

class MigrationRequest(BaseModel):
    from_version: str = Field(..., description="Version hiện tại")
    to_version: str = Field(..., description="Version muốn upgrade")
    force: bool = Field(default=False, description="Force migration ngay cả khi có lỗi")

class MigrationResponse(BaseModel):
    success: bool = Field(..., description="Trạng thái migration")
    message: str = Field(..., description="Thông báo kết quả")
    from_version: str = Field(..., description="Version trước migration")
    to_version: str = Field(..., description="Version sau migration")
    executed_at: datetime = Field(..., description="Thời gian thực hiện")
    details: Optional[str] = Field(None, description="Chi tiết migration")

class MigrationStatusResponse(BaseModel):
    current_version: str = Field(..., description="Version hiện tại")
    latest_version: str = Field(..., description="Version mới nhất")
    pending_migrations: List[str] = Field(default=[], description="Danh sách migration chưa chạy")
    is_up_to_date: bool = Field(..., description="Có phải version mới nhất không") 