from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
from datetime import datetime


class TopicCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Topic name")
    description: Optional[str] = Field(default=None)
    reclassify_lookback_day: int = Field(default=1) 


class TopicUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    reclassify_lookback_day: Optional[int] = Field(default=None)


class TopicResponse(BaseModel):
    id: int
    name: str
    last_classified_at: Optional[datetime] = None
    description: Optional[str] = None
    created_by: Optional[int] = None
    owner: Optional[Dict[str, Any]] = None
    is_deleted: bool = False
    file_total: Optional[int] = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None
        }


class TopicFileMatchRequest(BaseModel):
    topic_id: int = Field(..., gt=0)
    file_id: int = Field(..., gt=0)
