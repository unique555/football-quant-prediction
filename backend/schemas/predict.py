"""
Pydantic Schema: 预测请求/响应
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PredictRequest(BaseModel):
    """单场预测请求"""
    home_team: str
    away_team: str
    league: Optional[str] = None
    match_date: Optional[datetime] = None


class ScorelineProb(BaseModel):
    """比分概率"""
    scoreline: str       # e.g. "1-0"
    probability: float


class PredictResponse(BaseModel):
    """预测响应"""
    home_team: str
    away_team: str
    home_win_prob: float
    draw_prob: float
    away_win_prob: float
    top_scorelines: List[ScorelineProb] = []
    predicted_home_score: float
    predicted_away_score: float
    confidence: float
    model_version: str


class BatchPredictRequest(BaseModel):
    """批量预测请求"""
    league: str
    match_date: Optional[datetime] = None


class ErrorResponse(BaseModel):
    detail: str
