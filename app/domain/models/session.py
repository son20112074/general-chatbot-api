from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(Text, nullable=True, default="")
    user_id = Column(String(255), index=True, nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey(f'{settings.DB_SCHEMA}.projects.id'), index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    data = Column(Text, nullable=True)  # For storing session data as JSON string

    # Add relationship to project
    project = relationship("Project", back_populates="sessions")
    
    # Add relationships with cascade deletion
    chat_histories = relationship("ChatHistory", 
                                back_populates="session",
                                cascade="all, delete-orphan",
                                foreign_keys="ChatHistory.session_id",
                                primaryjoin="Session.session_id == ChatHistory.session_id")
    
    chat_messages = relationship("ChatMessage",
                               back_populates="session",
                               cascade="all, delete-orphan",
                               foreign_keys="ChatMessage.session_id",
                               primaryjoin="Session.session_id == ChatMessage.session_id")

    def __repr__(self):
        return f"<Session(session_id='{self.session_id}', name='{self.name}', user_id='{self.user_id}', project_id='{self.project_id}')>" 