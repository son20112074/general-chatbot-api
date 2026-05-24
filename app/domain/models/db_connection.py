from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean
from app.core.database import Base
from app.core.config import settings


class DBConnection(Base):
    __tablename__ = "db_connections"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    description = Column(String)
    type = Column(String)  # postgres | mysql
    host = Column(String)
    port = Column(Integer)
    username = Column(String)
    password = Column(String)
    database = Column(String)
    user_id = Column(String)
    instruction = Column(String)
    exposed = Column(String)  # public | private
    schema_cache = Column(JSON)  # VERY IMPORTANT
    is_connected = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
