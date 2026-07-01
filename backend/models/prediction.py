"""
SQLAlchemy ORM 模型：预测记录
"""

from core.database import Base
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    fixture_id = Column(Integer, index=True, comment="API-Football fixture ID")
    model_version = Column(String(50), comment="模型版本号")
    model_name = Column(String(50), comment="模型名称: poisson / stacking / ensemble")

    # 预测概率
    home_win_prob = Column(Float, comment="主胜概率")
    draw_prob = Column(Float, comment="平局概率")
    away_win_prob = Column(Float, comment="客胜概率")

    # 预测比分
    predicted_home_score = Column(Float, comment="预测主队进球")
    predicted_away_score = Column(Float, comment="预测客队进球")

    # 置信度
    confidence = Column(Float, comment="预测置信度 0-1")
    best_market = Column(String(50))
    best_pick = Column(String(120))
    best_display_pick = Column(String(160))
    best_odds = Column(Float)
    best_ev = Column(Float)
    best_kelly = Column(Float)
    value_score = Column(Integer)
    confidence_text = Column(String(20))
    risk = Column(String(20))
    report_text = Column(Text)
    raw_json = Column(JSONB)

    created_at = Column(DateTime, server_default=func.now())
