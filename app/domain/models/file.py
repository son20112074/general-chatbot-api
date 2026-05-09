from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import ARRAY, Boolean, Column, DateTime, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base


class ExtractionState(PyEnum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    FAILED = 'failed'
    DONE = 'done'


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index('files_hash_unique_active', 'hash', unique=True, postgresql_where='is_deleted = false'),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    size = Column(Integer, nullable=False)
    hash = Column(String(128), nullable=False)
    path = Column(Text, nullable=False)
    extension = Column(String(20), nullable=True)
    mime_type = Column(String(100), nullable=True)
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id'), nullable=True)

    folder_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.folders.id', ondelete='SET NULL'), nullable=True)
    role_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.roles.id', ondelete='SET NULL'), nullable=True)
    type = Column(String(15), nullable=False, default='private')
    node_path = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Processing fields
    is_processed = Column(Boolean, default=None, nullable=True)
    processing_duration = Column(Integer, nullable=True)
    content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)

    is_embedded = Column(Boolean, default=None, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=True)

    extraction_state = Column(
        SAEnum(
            ExtractionState,
            native_enum=False,
            length=20,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=ExtractionState.PENDING,
        nullable=False,
        server_default="'pending'",
    )

    extraction_attempts = Column(Integer, default=0, nullable=False, server_default='0')

    # Topic classification
    is_topic_classified = Column(Boolean, default=None, nullable=True)
    topic_classify_retries = Column(Integer, nullable=True, server_default='0')

    # Classification fields
    listed_nation = Column(ARRAY(String), nullable=True)
    important_news = Column(ARRAY(String), nullable=True)
    listed_technology = Column(ARRAY(String), nullable=True)
    listed_company = Column(ARRAY(String), nullable=True)
    listed_timeline = Column(ARRAY(String), nullable=True)
    responsible_departments = Column(ARRAY(String), nullable=True)

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])
    folder = relationship("Folder", foreign_keys=[folder_id])
    role = relationship("Role", foreign_keys=[role_id])

    def __repr__(self):
        return f"<File {self.name} ({self.id})>"

    @property
    def url(self) -> str:
        """Full public URL to access the file via storage."""
        if self.path:
            return f"{settings.STORAGE_PUBLIC_URL}/{settings.STORAGE_BUCKET_NAME}/{self.path}"
        return None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "size": self.size,
            "hash": self.hash,
            "path": self.path,
            "url": self.url,
            "extension": self.extension,
            "mime_type": self.mime_type,
            "created_by": self.created_by,
            "folder_id": self.folder_id,
            "role_id": self.role_id,
            "type": self.type,
            "node_path": self.node_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_processed": self.is_processed,
            "processing_duration": self.processing_duration,
            "content": self.content,
            "summary": self.summary,
            "is_embedded": self.is_embedded,
            "is_deleted": self.is_deleted,
            "extraction_state": (
                getattr(self, "extraction_state", None).value
                if getattr(self, "extraction_state", None) is not None and hasattr(getattr(self, "extraction_state", None), "value")
                else getattr(self, "extraction_state", None)
            ),
            "extraction_attempts": getattr(self, "extraction_attempts", 0),
            "listed_nation": self.listed_nation,
            "important_news": self.important_news,
            "listed_technology": self.listed_technology,
            "listed_company": self.listed_company,
            "listed_timeline": self.listed_timeline,
            "responsible_departments": self.responsible_departments,
            "is_topic_classified": self.is_topic_classified,
            "topic_classify_retries": getattr(self, "topic_classify_retries", 0),
        }
