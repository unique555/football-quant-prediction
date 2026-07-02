"""
价值投注路由 — 当日价值投注列表
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from models.match import Match
from models.prediction import Prediction
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

router = APIRouter()


@router.get("/value/today")
async def value_today(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """今日价值投注列表."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=2)

    rows = (
        (
            await db.execute(
                select(Prediction, Match)
                .outerjoin(Match, Prediction.match_id == Match.id)
                .where(
                    Prediction.created_at >= today_start,
                    Prediction.best_ev.is_not(None),
                    Prediction.best_ev > 0,
                    Prediction.settled_status == "pending",
                )
                .order_by(desc(Prediction.best_ev))
                .limit(min(limit, 100))
            )
        )
        .all()
    )
    return [
        {
            "id": pred.id,
            "fixture_id": pred.fixture_id,
            "home_team": match.home_team_name if match else None,
            "away_team": match.away_team_name if match else None,
            "league": match.league_name if match else None,
            "kickoff": match.match_date.isoformat() if match and match.match_date else None,
            "best_pick": pred.best_display_pick,
            "best_odds": pred.best_odds,
            "best_ev": pred.best_ev,
            "best_edge": pred.best_edge,
            "best_kelly": pred.best_kelly,
            "risk": pred.risk,
            "value_score": pred.value_score,
            "settled_status": pred.settled_status,
        }
        for pred, match in rows
    ]
