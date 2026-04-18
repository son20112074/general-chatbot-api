from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, ARRAY, Index
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

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
    is_graph_extracted = Column(Boolean, default=False, nullable=False, server_default="false")

    # Classification fields
    listed_nation = Column(ARRAY(String), nullable=True)
    important_news = Column(ARRAY(String), nullable=True)
    listed_technology = Column(ARRAY(String), nullable=True)
    listed_company = Column(ARRAY(String), nullable=True)

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
            "listed_nation": self.listed_nation,
            "important_news": self.important_news,
            "listed_technology": self.listed_technology,
            "listed_company": self.listed_company,
        }
