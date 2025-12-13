from sqlalchemy import Column, Integer, String, DateTime, Text, Index, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base
from app.core.config import settings

class ChatMessageType(str, enum.Enum):
    """Enum for message types."""
    USER = "user"
    BOT = "bot"

class ChatMessage(Base):
    """Model for chat messages."""
    __tablename__ = "chat_messages"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey(f'{settings.DB_SCHEMA}.sessions.session_id'), nullable=False, index=True)
    data = Column(Text, nullable=True)
    type = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Add relationship to session
    session = relationship("Session", back_populates="chat_messages")

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, session_id={self.session_id}, type={self.type})>" 