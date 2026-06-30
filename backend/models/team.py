"""
SQLAlchemy ORM 模型：球队
"""

from core.database import Base
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func


class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, comment="球队名称")
    league_id = Column(Integer, ForeignKey("leagues.id"), comment="所属联赛")
    elo_rating = Column(Float, comment="ELO评分")
    xg_for_avg = Column(Float, comment="近10场xG均值")
    xg_against_avg = Column(Float, comment="近10场xGA均值")
    form_score = Column(Float, comment="近期战绩得分")
    external_id = Column(String(50), comment="外部API对应ID")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
