from datetime import datetime
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, CheckConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class PersonalTaskStatus(Base):
    __tablename__ = "personal_task_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.tasks.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id', ondelete='CASCADE'), nullable=False)
    status = Column(String(20), nullable=False, default='new')
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    # Relationships
    task = relationship("Task")
    user = relationship("User")

    __table_args__ = (
        CheckConstraint("status IN ('new', 'in_progress', 'completed')", name='check_personal_task_status'),
        {"schema": settings.DB_SCHEMA}
    )

    def to_dict(self) -> dict:
        """Convert model instance to dictionary"""
        return {
            'id': self.id,
            'task_id': self.task_id,
            'user_id': self.user_id,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        } 