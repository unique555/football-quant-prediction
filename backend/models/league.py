"""
SQLAlchemy ORM 模型：联赛
"""

from core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, func


class League(Base):
    __tablename__ = "leagues"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="联赛名称")
    country = Column(String(100), comment="国家")
    tier = Column(Integer, default=1, comment="级别")
    api_source = Column(String(50), comment="数据来源: api-football / odds-api")
    external_id = Column(String(50), comment="外部API对应ID")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
