from datetime import datetime
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Text, Boolean, Index
from app.core.database import Base
from app.core.config import settings


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        Index(
            "idx_stores_name_owner_active",
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
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "is_deleted": self.is_deleted,
            "created_by": self.created_by if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
