from sqlalchemy import Column, Integer, String, Text, ARRAY, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class ChatHistory(Base):
    __tablename__ = "chat_histories"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(255), ForeignKey(f'{settings.DB_SCHEMA}.sessions.session_id'), nullable=False, index=True)
    message_id = Column(String(255), unique=True, index=True, nullable=False)
    content = Column(Text, nullable=True)
    instruct_content = Column(Text, nullable=True)
    role = Column(String(50), nullable=False)
    cause_by = Column(String(100), nullable=True)
    sent_from = Column(String(255), nullable=True)
    send_to = Column(ARRAY(String), nullable=True)  # List of strings
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Add relationship to session
    session = relationship("Session", back_populates="chat_histories")

    def __repr__(self):
        return f"<ChatHistory(message_id='{self.message_id}', role='{self.role}')>" 