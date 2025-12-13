from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FirstMessageResponse(BaseModel):
    session_id: str
    id: int
    data: Optional[str] = None
    type: str
    created_at: datetime
