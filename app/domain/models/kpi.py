from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text, Float
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class EmployeeKPI(Base):
    __tablename__ = "employee_kpis"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.users.id"), nullable=False)
    
    # Loại kỳ (ngày, tháng, quý, năm)
    period_type = Column(String(20), nullable=False)  # 'daily', 'monthly', 'quarterly', 'yearly'
    period_value = Column(String(50), nullable=False)  # Giá trị của kỳ (VD: '2024-01', 'Q1-2024', '2024')
    
    # KPI tự động (có thể được tính toán từ hệ thống)
    auto_kpi = Column(Float, nullable=True)
    
    # KPI user tự đánh giá
    user_self_assessment = Column(Float, nullable=True)
    user_assessment_reason = Column(Text, nullable=True)  # Lý do user đánh giá
    user_assessment_time = Column(DateTime, nullable=True)  # Thời gian user đánh giá
    
    # KPI do cấp trên đánh giá
    manager_assessment = Column(Float, nullable=True)
    manager_assessment_reason = Column(Text, nullable=True)  # Lý do cấp trên đánh giá
    manager_assessment_time = Column(DateTime, nullable=True)  # Thời gian cấp trên đánh giá
    assessed_by = Column(Integer, ForeignKey(f"{settings.DB_SCHEMA}.users.id"), nullable=True)  # Người đánh giá
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="kpis")
    manager = relationship("User", foreign_keys=[assessed_by], backref="assessed_kpis")

    def __repr__(self):
        return f"<EmployeeKPI {self.user_id} - {self.period_type} {self.period_value}>"
        
    def to_dict(self):
        """Convert KPI object to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "period_type": self.period_type,
            "period_value": self.period_value,
            "auto_kpi": self.auto_kpi,
            "user_self_assessment": self.user_self_assessment,
            "user_assessment_reason": self.user_assessment_reason,
            "user_assessment_time": self.user_assessment_time.isoformat() if self.user_assessment_time else None,
            "manager_assessment": self.manager_assessment,
            "manager_assessment_reason": self.manager_assessment_reason,
            "manager_assessment_time": self.manager_assessment_time.isoformat() if self.manager_assessment_time else None,
            "assessed_by": self.assessed_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        } 