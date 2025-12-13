from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
from app.core.config import settings

class TaskWork(Base):
    __tablename__ = "task_works"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    content = Column(Text)
    image_links = Column(JSON, default=list)  # List of image URLs
    file_links = Column(JSON, default=list)   # List of file URLs
    attributes = Column(JSON, default=dict)   # Key-value attributes
    is_difficult = Column(Boolean, default=False)  # New field for difficulty flag
    task_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.tasks.id'), nullable=True)
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    task = relationship("Task", back_populates="works")
    creator = relationship("User", foreign_keys=[created_by])

    def to_dict(self) -> dict:
        """Convert model instance to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'content': self.content,
            'image_links': self.image_links,
            'file_links': self.file_links,
            'attributes': self.attributes,
            'task_id': self.task_id,
            'is_difficult': self.is_difficult,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        } 