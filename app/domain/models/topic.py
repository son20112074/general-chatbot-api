from datetime import datetime
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Text, Boolean, Index
from app.core.database import Base
from app.core.config import settings


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        Index(
            "idx_topics_name_owner_active",
            "name", 
            "created_by",
            unique=True,
            postgresql_where=(Column("is_deleted") == False),
        ),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)
    last_classified_at = Column(DateTime, nullable=True, default=None)
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'), nullable=True)
    reclassify_lookback_day = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_deleted": self.is_deleted,
            "last_classified_at": self.last_classified_at.isoformat() if self.last_classified_at else None,
            "created_by": self.created_by if self.created_by else None,
            "reclassify_lookback_day": self.reclassify_lookback_day if self.reclassify_lookback_day else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
