from datetime import datetime
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from app.core.database import Base
from app.core.config import settings


class StoreFile(Base):
    __tablename__ = "store_files"
    __table_args__ = (
        UniqueConstraint("file_id", "store_id", name="uq_store_file"),
        Index("idx_store_files_store_id", "store_id"),
        Index("idx_store_files_file_id", "file_id"),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.files.id", ondelete="CASCADE"), nullable=False)
    store_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.stores.id", ondelete="CASCADE"), nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=None, onupdate=datetime.utcnow)
