from datetime import datetime
from sqlalchemy import ARRAY, Column, Integer, String, DateTime, ForeignKey, Boolean, Text, CheckConstraint, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    type = Column(String(20), nullable=False)
    priority = Column(String(20), default='medium')
    status = Column(String(20), default='new')
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)
    
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'))
    
    assigned_to = Column(ARRAY(Integer))  # Array of user IDs
    file_list = Column(ARRAY(String))  # Array of file strings
    file_name_list = Column(ARRAY(String))  # Array of file name strings
    
    parent_path = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    works = relationship("TaskWork", back_populates="task")

    __table_args__ = (
        CheckConstraint("type IN ('recurring', 'ad_hoc')", name='check_task_type'),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name='check_task_priority'),
        CheckConstraint("status IN ('new', 'in_progress', 'pending_approval', 'completed', 'overdue', 'paused', 'cancelled')", name='check_task_status'),
        CheckConstraint("progress BETWEEN 0 AND 100", name='check_task_progress'),
        {"schema": settings.DB_SCHEMA}
    )

    def to_dict(self) -> dict:
        """Convert model instance to dictionary"""
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'type': self.type,
            'priority': self.priority,
            'status': self.status,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'end_date': self.end_date.isoformat() if self.end_date else None,
            'progress': self.progress,
            'created_by': self.created_by,
            'assigned_to': self.assigned_to if self.assigned_to else [],
            'file_list': self.file_list if self.file_list else [],
            'file_name_list': self.file_name_list if self.file_name_list else [],
            'parent_path': self.parent_path,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

 