"""
SQLAlchemy ORM 模型：赔率
"""

from core.database import Base
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func


class Odds(Base):
    __tablename__ = "odds"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    bookmaker = Column(String(100), nullable=False, comment="博彩公司名称")
    home_win_odds = Column(Float, comment="主胜赔率")
    draw_odds = Column(Float, comment="平局赔率")
    away_win_odds = Column(Float, comment="客胜赔率")
    over_25_odds = Column(Float, comment="大2.5球赔率")
    btts_odds = Column(Float, comment="双方进球赔率")
    timestamp = Column(DateTime, server_default=func.now(), comment="赔率抓取时间")
