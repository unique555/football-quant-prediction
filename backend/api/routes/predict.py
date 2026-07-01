"""
预测路由 — 单场 & 批量预测
"""

from fastapi import APIRouter, Depends
from models.match import Match
from models.prediction import Prediction
from services.prediction_service import PredictionService
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

router = APIRouter()


@router.post("/predict")
async def predict_match(payload: dict, db: AsyncSession = Depends(get_db)):
    """单场比赛预测."""
    query = (
        payload.get("query") or f"{payload.get('home_team', '')} vs {payload.get('away_team', '')}"
    )
    service = PredictionService()
    result = await service.resolve_text(db, query)
    return {
        "status": result.status,
        "message": result.message,
        "fixture_id": result.fixture_id,
        "payload": result.payload,
    }


@router.post("/predict/batch")
async def predict_batch():
    """批量预测（一轮比赛）→ 待实现"""
    return {"status": "not_implemented", "endpoint": "/v1/predict/batch"}


@router.get("/predictions/recent")
async def recent_predictions(limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Prediction, Match)
        .outerjoin(Match, Prediction.match_id == Match.id)
        .order_by(desc(Prediction.created_at))
        .limit(min(limit, 100))
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": pred.id,
            "fixture_id": pred.fixture_id,
            "home_team": match.home_team_name if match else None,
            "away_team": match.away_team_name if match else None,
            "league": match.league_name if match else None,
            "kickoff": match.match_date.isoformat() if match and match.match_date else None,
            "best_pick": pred.best_display_pick,
            "best_market": pred.best_market,
            "best_odds": pred.best_odds,
            "best_ev": pred.best_ev,
            "best_kelly": pred.best_kelly,
            "best_edge": pred.best_edge,
            "best_bookmaker": pred.best_bookmaker,
            "market_prob": pred.market_prob,
            "value_score": pred.value_score,
            "risk": pred.risk,
            "settled_status": pred.settled_status,
            "profit_units": pred.profit_units,
            "created_at": pred.created_at.isoformat() if pred.created_at else None,
        }
        for pred, match in rows
    ]
