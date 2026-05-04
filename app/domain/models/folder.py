from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.folders.id', ondelete='CASCADE'), nullable=True)
    parent_path = Column(Text, nullable=True)

    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'), nullable=False)
    role_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.roles.id', ondelete='SET NULL'), nullable=True)
    type = Column(String(15), nullable=False, default='private')

    description = Column(Text, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    role = relationship("Role", foreign_keys=[role_id])
    parent = relationship("Folder", remote_side=[id], foreign_keys=[parent_id])

    def __repr__(self):
        return f"<Folder {self.name} ({self.id})>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "parent_path": self.parent_path,
            "created_by": self.created_by,
            "role_id": self.role_id,
            "type": self.type,
            "description": self.description,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
