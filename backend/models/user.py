"""
SQLAlchemy ORM 模型：用户
"""

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, func


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(200), unique=True, nullable=False)
    hashed_password = Column(String(200), nullable=False)
    subscription = Column(String(20), default="free", comment="free | pro | enterprise")
    is_active = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
