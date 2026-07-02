"""
SQLAlchemy ORM 模型：模型版本
"""

from core.database import Base
from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, func


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_tag = Column(String(50), unique=True, nullable=False)
    model_type = Column(String(50), comment="stacking_lgb_xgb_catboost")
    accuracy = Column(Float)
    brier_score = Column(Float)
    log_loss = Column(Float)
    features_hash = Column(String(64))
    training_samples = Column(Integer)
    is_active = Column(Boolean, default=False)
    mlflow_run_id = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())
