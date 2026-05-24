from datetime import datetime
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from app.core.database import Base
from app.core.config import settings


class SharedStore(Base):
    __tablename__ = "shared_store"
    __table_args__ = (
        UniqueConstraint("store_id", "user_id", name="uq_shared_store"),
        Index("idx_shared_store_store_id", "store_id"),
        Index("idx_shared_store_user_id", "user_id"),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    store_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.stores.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.users.id", ondelete="CASCADE"), nullable=False)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=None, onupdate=datetime.utcnow)
