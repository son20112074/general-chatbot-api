from datetime import datetime
from sqlalchemy import Column, DateTime, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings
import uuid

class Node(Base):
    __tablename__ = "nodes"
    __table_args__ = (
        UniqueConstraint("name", "entity_type", name="uq_node_name_type"),
        Index("ix_nodes_entity_type_created_at", "entity_type", "created_at"),
        Index("ix_nodes_created_at", "created_at"),
        {"schema": settings.DB_SCHEMA},
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    entity_type = Column(Text, nullable=False)
    attributes = Column(JSONB, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow)
