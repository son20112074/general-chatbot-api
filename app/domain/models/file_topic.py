from datetime import datetime
from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from app.core.database import Base
from app.core.config import settings


class FileTopic(Base):
    __tablename__ = "file_topics"
    __table_args__ = (
        UniqueConstraint("file_id", "topic_id", name="uq_file_topic"),
        Index("idx_file_topics_topic_id", "topic_id"),
        Index("idx_file_topics_file_id", "file_id"),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.files.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.topics.id", ondelete="CASCADE"), nullable=False)
    is_matched = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
