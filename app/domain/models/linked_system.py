from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text

from app.core.config import settings
from app.core.database import Base


class LinkedSystem(Base):
    __tablename__ = "linked_systems"
    __table_args__ = (
        Index(
            "idx_linked_systems_abbr_active",
            "abbr",
            unique=True,
            postgresql_where=(Column("is_deleted") == False),  # noqa: E712
        ),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    abbr = Column(String(32), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(64), nullable=False, default="appstore")
    url = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_deleted = Column(Boolean, default=False, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey(f"{settings.DB_SCHEMA}.users.id"),
        nullable=True,
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "abbr": self.abbr,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "url": self.url,
            "sort_order": self.sort_order,
            "is_deleted": self.is_deleted,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
