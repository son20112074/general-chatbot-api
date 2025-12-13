from typing import Dict, Any, Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


class HomeUpdate(BaseModel):
    """Schema for updating an existing device"""
    name: Optional[str] = None
    altitude: Optional[int] = Field(None, description="Altitude in meters above sea level")
    coordinates: Optional[List[float]] = Field(None, description="Array with [longitude, latitude]")
    timezone: Optional[str] = Field(None, description="Timezone string (e.g., 'America/New_York')")