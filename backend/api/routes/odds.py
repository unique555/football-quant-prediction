"""
赔率路由 — 实时赔率查询
"""

from fastapi import APIRouter, Depends
from models.telegram_mvp import OddsSnapshot
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

router = APIRouter()


@router.get("/odds/{match_id}")
async def match_odds(match_id: str, db: AsyncSession = Depends(get_db)):
    """单场赔率快照."""
    fixture_id = int(match_id)
    rows = (
        await db.execute(
            select(OddsSnapshot)
            .where(OddsSnapshot.fixture_id == fixture_id)
            .order_by(desc(OddsSnapshot.captured_at))
            .limit(100)
        )
    ).scalars().all()
    return [
        {
            "fixture_id": row.fixture_id,
            "market": row.market,
            "bookmaker": row.bookmaker,
            "home_odds": row.home_odds,
            "draw_odds": row.draw_odds,
            "away_odds": row.away_odds,
            "ah_line": row.ah_line,
            "ah_home_odds": row.ah_home_odds,
            "ah_away_odds": row.ah_away_odds,
            "ou_line": row.ou_line,
            "over_odds": row.over_odds,
            "under_odds": row.under_odds,
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        }
        for row in rows
    ]
