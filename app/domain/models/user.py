from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.core.config import settings

class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": settings.DB_SCHEMA}

    id = Column(Integer, primary_key=True, autoincrement=True)
    account_name = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=False, nullable=True)
    role_id = Column(Integer, nullable=True)
    password = Column(String(255), nullable=False)
    avatar = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(Integer, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    full_name = Column(String(100), nullable=False)
    status = Column(Boolean, default=True, nullable=True)

    # Relationships
    # role = relationship("Role", back_populates="users")
    # creator = relationship("User", remote_side=[id], backref="created_users")

    def __repr__(self):
        return f"<User {self.account_name}>"
        
    def to_dict(self):
        """Convert user object to dictionary"""
        return {
            "id": self.id,
            "account_name": self.account_name,
            "email": self.email,
            "role_id": self.role_id,
            "avatar": self.avatar,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "full_name": self.full_name,
            "status": self.status
        } 