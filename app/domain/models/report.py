from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base


class ReportStatusEnum(PyEnum):
    COMPILING = 'compiling'
    COMPLETED = 'completed'
    FAILED = 'failed'


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    template_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.report_templates.id', ondelete='SET NULL'), nullable=True)
    content = Column(Text, nullable=True)
    status = Column(
        SAEnum(ReportStatusEnum, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        default=ReportStatusEnum.COMPILING,
        nullable=False,
        server_default="'compiling'",
    )
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    file_url = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    template = relationship("ReportTemplate", back_populates="reports", foreign_keys=[template_id])
    creator = relationship("User", foreign_keys=[created_by])
    documents = relationship("ReportDocument", back_populates="report", cascade="all, delete-orphan")
