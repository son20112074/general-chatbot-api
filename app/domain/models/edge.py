from datetime import datetime
from sqlalchemy import Column, Integer, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings
import uuid

class Edge(Base):
    __tablename__ = "edges"
    __table_args__ = (
        UniqueConstraint("source_node_id", "target_node_id", "edge_type", name="uq_edge_src_tgt_type"),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey(f'{settings.DB_SCHEMA}.nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey(f'{settings.DB_SCHEMA}.nodes.id', ondelete='CASCADE'), nullable=False, index=True)
    edge_type = Column(Text, nullable=False)
    fact = Column(Text, nullable=True)
    attributes = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow)
    file_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.files.id', ondelete='SET NULL'), nullable=True, index=True)

    source_node = relationship("Node", foreign_keys=[source_node_id])
    target_node = relationship("Node", foreign_keys=[target_node_id])
    file = relationship("File", foreign_keys=[file_id])
