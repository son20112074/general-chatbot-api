from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import ARRAY, Boolean, Column, Date, DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import relationship

from app.core.config import settings
from app.core.database import Base


class FrequencyEnum(PyEnum):
    DAILY = 'daily'
    WEEKLY = 'weekly'
    MONTHLY = 'monthly'
    QUARTERLY = 'quarterly'


# class CreationDayEnum(PyEnum):
#     TODAY = 'today'
#     TOMORROW = 'tomorrow'


class FileModeEnum(PyEnum):
    SELECT = 'select'
    BY_PERIOD = 'by_period'


class ReportTemplate(Base):
    __tablename__ = "report_templates"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    frequency = Column(
        SAEnum(FrequencyEnum, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # creation_day = Column(
    #     SAEnum(CreationDayEnum, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
    #     nullable=True,
    # )
    creation_time = Column(Time, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_indefinite = Column(Boolean, default=True, nullable=False, server_default='true')
    file_mode = Column(
        SAEnum(FileModeEnum, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=FileModeEnum.BY_PERIOD,
        server_default='by_period',
    )
    is_use_timeline = Column(Boolean, default=False, nullable=False, server_default='false')
    file_ids = Column(ARRAY(Integer), nullable=True)
    created_by = Column(Integer, ForeignKey(f'{settings.DB_SCHEMA}.users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    creator = relationship("User", foreign_keys=[created_by])
    reports = relationship("Report", back_populates="template")
