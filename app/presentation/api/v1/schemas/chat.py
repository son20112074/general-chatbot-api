from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FirstMessageResponse(BaseModel):
    session_id: str
    id: int
    data: Optional[str] = None
    type: str
    source_path: Optional[str] = None
    created_at: datetime
