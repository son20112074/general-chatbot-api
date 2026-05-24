from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class DBConnectionBase(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = Field(None, description="postgres | mysql")
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    instruction: Optional[str] = None
    exposed: Optional[str] = Field(None, description="public | private")

class DBConnectionCreate(DBConnectionBase):
    name: str
    type: str
    host: str
    port: int
    username: str
    password: str
    database: str
    user_id: Optional[str] = None


class DBConnectionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = Field(None, description="postgres | mysql")
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    database: Optional[str] = None
    user_id: Optional[str] = None
    instruction: Optional[str] = None
    exposed: Optional[str] = Field(None, description="public | private")
    schema_cache: Optional[Dict[str, Any]] = None
    is_connected: Optional[bool] = None


class DBConnectionResponse(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = Field(None, description="postgres | mysql")
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    database: Optional[str] = None
    instruction: Optional[str] = None
    exposed: Optional[str] = Field(None, description="public | private")
    user_id: Optional[str] = None
    schema_cache: Optional[Dict[str, Any]] = None
    is_connected: Optional[bool] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DBConnectionQuery(BaseModel):
    type: Optional[str] = None
    exposed: Optional[str] = None
    search_text: Optional[str] = None
    is_connected: Optional[bool] = None
    ids: Optional[List[int]] = None
    page: int = 1
    page_size: int = 10


class DBConnectionAskRequest(BaseModel):
    question: str
    connection_ids: List[int]


class DBConnectionAskResponse(BaseModel):
    answer: Optional[str]
