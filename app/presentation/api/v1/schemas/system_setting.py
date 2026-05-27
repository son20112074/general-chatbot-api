from datetime import datetime
from pydantic import BaseModel, Field


class SystemSettingUpsertRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=255)
    value: str | None = None


class SystemSettingResponse(BaseModel):
    key: str
    value: str | None
    created_at: datetime
    updated_at: datetime
    created_by: int | None = None

    class Config:
        from_attributes = True
