from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    level = Column(Integer, nullable=False)
    parent_path = Column(Text)
    description = Column(Text)
    created_by = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert the role model to a clean dictionary without SQLAlchemy internal variables."""
        return {
            "id": self.id,
            "name": self.name,
            "level": self.level,
            "parent_path": self.parent_path,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

