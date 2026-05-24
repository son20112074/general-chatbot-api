from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base
from app.core.config import settings

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    user_id = Column(String(255), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    is_active = Column(Boolean, default=True)

    # Add relationship to sessions
    sessions = relationship(
        "Session",
        back_populates="project",
        lazy="selectin",
        order_by="desc(Session.created_at)"
    )

    def __repr__(self):
        return f"<Project(id='{self.id}', name='{self.name}', user_id='{self.user_id}')>" 