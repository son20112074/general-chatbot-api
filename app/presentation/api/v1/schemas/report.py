from datetime import date, datetime, time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Report Template ───────────────────────────────────────────────────────────

class ReportTemplateCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    frequency: str = Field(..., description="daily | weekly | monthly | quarterly")
    creation_time: Optional[time] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_indefinite: bool = True
    is_use_timeline: bool = False
    file_mode: Literal["select", "by_period"] = "by_period"
    file_ids: Optional[List[int]] = None

    @field_validator("creation_time")
    @classmethod
    def validate_creation_time(cls, v: Optional[time]) -> Optional[time]:
        if v is not None and (v <= time(0, 0, 0) or v > time(23, 59, 59)):
            raise ValueError("creation_time must be between 00:00:01 and 23:59:59")
        return v


class ReportTemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    frequency: Optional[str] = None
    creation_time: Optional[time] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_indefinite: Optional[bool] = None
    is_use_timeline: Optional[bool] = None
    file_mode: Optional[Literal["select", "by_period"]] = None
    file_ids: Optional[List[int]] = None

    @field_validator("creation_time")
    @classmethod
    def validate_creation_time(cls, v: Optional[time]) -> Optional[time]:
        if v is not None and (v <= time(0, 0, 0) or v > time(23, 59, 59)):
            raise ValueError("creation_time must be between 00:00:01 and 23:59:59")
        return v


class ReportTemplateResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    frequency: str
    creation_time: Optional[time] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    is_indefinite: bool
    is_use_timeline: bool = False
    file_mode: str = "by_period"
    file_ids: Optional[List[int]] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Report ────────────────────────────────────────────────────────────────────

class ReportDocumentCreate(BaseModel):
    document_id: Optional[int] = None
    document_name: Optional[str] = None


class ReportDocumentItem(BaseModel):
    id: int
    document_id: Optional[int] = None
    document_name: Optional[str] = None
    user_id: Optional[int] = None
    status: Optional[str] = None

    class Config:
        from_attributes = True


class ReportResponse(BaseModel):
    id: int
    name: str
    template_id: Optional[int] = None
    template_name: Optional[str] = None
    frequency: Optional[str] = None
    content: Optional[str] = None
    status: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    file_url: Optional[str] = None
    created_by: Optional[int] = None
    creator_name: Optional[str] = None
    created_at: datetime
    document_count: int = 0
    documents: List[ReportDocumentItem] = []

    class Config:
        from_attributes = True

