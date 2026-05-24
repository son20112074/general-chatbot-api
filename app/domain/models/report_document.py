from enum import Enum as PyEnum

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base


class ReportDocumentStatus(PyEnum):
    QUEUING = 'queuing'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    ERROR = 'error'


class ReportDocument(Base):
    __tablename__ = "report_documents"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.reports.id', ondelete='CASCADE'), nullable=False)
    document_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.files.id', ondelete='SET NULL'), nullable=True)
    document_name = Column(String(255), nullable=True)
    user_id = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id', ondelete='SET NULL'), nullable=True)
    status = Column(
        SAEnum(ReportDocumentStatus, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        default=ReportDocumentStatus.QUEUING,
        nullable=False,
        server_default="'queuing'",
    )

    report = relationship("Report", back_populates="documents", foreign_keys=[report_id])
    file = relationship("File", foreign_keys=[document_id])
