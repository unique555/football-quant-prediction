"""
SQLAlchemy ORM 模型：比赛
"""

from core.database import Base
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    league_id = Column(Integer, ForeignKey("leagues.id"), nullable=False)
    match_date = Column(DateTime, nullable=False, comment="比赛时间(UTC)")
    status = Column(String(20), default="scheduled", comment="scheduled | live | finished")
    home_score = Column(Integer, comment="全场主队进球")
    away_score = Column(Integer, comment="全场客队进球")
    ht_home_score = Column(Integer, comment="半场主队进球")
    ht_away_score = Column(Integer, comment="半场客队进球")
    venue = Column(String(300), comment="球场名称")
    attendance = Column(Integer, comment="观众人数")
    external_id = Column(String(50), comment="外部API对应ID")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
