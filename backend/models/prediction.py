"""
SQLAlchemy ORM 模型：预测记录
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, func

from core.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
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

    created_at = Column(DateTime, server_default=func.now())
