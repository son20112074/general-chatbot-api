from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, ARRAY
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class File(Base):
    __tablename__ = "files"
    __table_args__ = {"schema": settings.DB_SCHEMA}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    size = Column(Integer, nullable=False)
    hash = Column(String(64), nullable=False, unique=True)
    path = Column(Text, nullable=False)
    extension = Column(String(20), nullable=True)
    mime_type = Column(String(100), nullable=True)
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Processing fields
    is_processed = Column(Boolean, default=None, nullable=True)
    processing_duration = Column(Integer, nullable=True)  # Processing duration in seconds
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)  # Will store AI-generated summary

    is_embedded = Column(Boolean, default=None, nullable=True)

    # Classification fields - array of strings
    listed_nation = Column(ARRAY(String), nullable=True)
    important_news = Column(ARRAY(String), nullable=True)
    listed_technology = Column(ARRAY(String), nullable=True)
    listed_company = Column(ARRAY(String), nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<File {self.name} ({self.id})>"
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "hash": self.hash,
            "path": self.path,
            "extension": self.extension,
            "mime_type": self.mime_type,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_processed": self.is_processed,
            "processing_duration": self.processing_duration,
            "content": self.content,
            "summary": self.summary,
            "is_embedded": self.is_embedded,
            "listed_nation": self.listed_nation,
            "important_news": self.important_news,
            "listed_technology": self.listed_technology,
            "listed_company": self.listed_company
        } 