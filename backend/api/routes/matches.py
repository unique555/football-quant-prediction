"""
比赛路由 — 赛程、详情、H2H
"""

from fastapi import APIRouter, Depends, HTTPException
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import OddsSnapshot, Result, ValueCandidate
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

router = APIRouter()


@router.get("/matches")
async def list_matches(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """最近入库比赛."""
    rows = (
        await db.execute(select(Match).order_by(desc(Match.match_date)).limit(min(limit, 100)))
    ).scalars().all()
    return [
        {
            "id": row.id,
            "fixture_id": row.api_fixture_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "league": row.league_name,
            "kickoff": row.match_date.isoformat() if row.match_date else None,
            "status": row.status,
            "score": f"{row.home_score}-{row.away_score}" if row.home_score is not None else None,
        }
        for row in rows
    ]


@router.get("/matches/{match_id}")
async def match_detail(match_id: str, db: AsyncSession = Depends(get_db)):
    """比赛详情."""
    fixture_id = int(match_id)
    match = (
        await db.execute(select(Match).where(Match.api_fixture_id == fixture_id))
    ).scalar_one_or_none()
    if not match:
        raise HTTPException(status_code=404, detail="match not found")
    predictions = (
        await db.execute(
            select(Prediction).where(Prediction.fixture_id == fixture_id).order_by(desc(Prediction.created_at)).limit(5)
        )
    ).scalars().all()
    candidates = (
        await db.execute(
            select(ValueCandidate).where(ValueCandidate.fixture_id == fixture_id).order_by(desc(ValueCandidate.created_at)).limit(20)
        )
    ).scalars().all()
    snapshots = (
        await db.execute(
            select(OddsSnapshot).where(OddsSnapshot.fixture_id == fixture_id).order_by(desc(OddsSnapshot.captured_at)).limit(30)
        )
    ).scalars().all()
    result = (
        await db.execute(select(Result).where(Result.fixture_id == fixture_id))
    ).scalar_one_or_none()
    return {
        "fixture_id": fixture_id,
        "home_team": match.home_team_name,
        "away_team": match.away_team_name,
        "league": match.league_name,
        "kickoff": match.match_date.isoformat() if match.match_date else None,
        "status": match.status,
        "result": {
            "home_goals": result.home_goals,
            "away_goals": result.away_goals,
            "status": result.status,
        }
        if result
        else None,
        "predictions": [
            {
                "best_pick": item.best_display_pick,
                "value_score": item.value_score,
                "risk": item.risk,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "report_text": item.report_text,
            }
            for item in predictions
        ],
        "value_candidates": [
            {
                "market": item.market,
                "pick": item.display_pick,
                "ev": item.ev,
                "kelly": item.kelly,
                "edge": item.edge,
                "value_score": item.value_score,
                "selected": item.selected,
            }
            for item in candidates
        ],
        "odds_snapshots": [
            {
                "market": item.market,
                "bookmaker": item.bookmaker,
                "home_odds": item.home_odds,
                "draw_odds": item.draw_odds,
                "away_odds": item.away_odds,
                "ah_line": item.ah_line,
                "ou_line": item.ou_line,
                "captured_at": item.captured_at.isoformat() if item.captured_at else None,
            }
            for item in snapshots
        ],
    }


@router.get("/teams/{team_id}/profile")
async def team_profile(team_id: str):
    """球队画像 → 待实现"""
    return {"status": "not_implemented", "team_id": team_id}


@router.get("/teams/{team_id}/h2h/{opponent_id}")
async def head_to_head(team_id: str, opponent_id: str):
    """历史交锋 → 待实现"""
    return {"status": "not_implemented", "team_id": team_id, "opponent_id": opponent_id}
