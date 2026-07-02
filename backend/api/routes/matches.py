"""
比赛路由 — 赛程、详情、H2H
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import OddsSnapshot, Result, ValueCandidate
from services.display_names import team_display_name_map, team_display_pair
from services.frontend_view import build_market_cards, build_report_template
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_db

router = APIRouter()


@router.get("/matches")
async def list_matches(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """最近入库比赛."""
    rows = (
        (await db.execute(select(Match).order_by(desc(Match.match_date)).limit(min(limit, 100))))
        .scalars()
        .all()
    )
    display_names = await team_display_name_map(
        db,
        [name for row in rows for name in (row.home_team_name, row.away_team_name)],
    )
    return [
        {
            "id": row.id,
            "fixture_id": row.api_fixture_id,
            "home_team": row.home_team_name,
            "away_team": row.away_team_name,
            "home_team_zh": display_names.get(row.home_team_name or "", row.home_team_name),
            "away_team_zh": display_names.get(row.away_team_name or "", row.away_team_name),
            "league": row.league_name,
            "kickoff": row.match_date.isoformat() if row.match_date else None,
            "status": row.status,
            "score": f"{row.home_score}-{row.away_score}" if row.home_score is not None else None,
        }
        for row in rows
    ]


@router.get("/matches/today")
async def today_matches(db: AsyncSession = Depends(get_db)):
    """今日已知比赛与分析状态."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = (
        (
            await db.execute(
                select(Match)
                .where(Match.match_date >= start, Match.match_date < end)
                .order_by(Match.match_date)
            )
        )
        .scalars()
        .all()
    )
    display_names = await team_display_name_map(
        db,
        [name for match in rows for name in (match.home_team_name, match.away_team_name)],
    )
    items = []
    for match in rows:
        pred = (
            await db.execute(
                select(Prediction)
                .where(Prediction.fixture_id == match.api_fixture_id)
                .order_by(desc(Prediction.created_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        result = (
            await db.execute(select(Result).where(Result.fixture_id == match.api_fixture_id))
        ).scalar_one_or_none()
        items.append(
            {
                "fixture_id": match.api_fixture_id,
                "home_team": match.home_team_name,
                "away_team": match.away_team_name,
                "home_team_zh": display_names.get(match.home_team_name or "", match.home_team_name),
                "away_team_zh": display_names.get(match.away_team_name or "", match.away_team_name),
                "league": match.league_name,
                "kickoff": match.match_date.isoformat() if match.match_date else None,
                "status": match.status,
                "analyzed": pred is not None,
                "best_pick": pred.best_display_pick if pred else None,
                "value_score": pred.value_score if pred else None,
                "risk": pred.risk if pred else None,
                "review_status": pred.settled_status if pred else "pending",
                "score": f"{result.home_goals}-{result.away_goals}"
                if result and result.home_goals is not None
                else None,
            }
        )
    return items


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
        (
            await db.execute(
                select(Prediction)
                .where(Prediction.fixture_id == fixture_id)
                .order_by(desc(Prediction.created_at))
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    candidates = (
        (
            await db.execute(
                select(ValueCandidate)
                .where(ValueCandidate.fixture_id == fixture_id)
                .order_by(desc(ValueCandidate.created_at))
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    snapshots = (
        (
            await db.execute(
                select(OddsSnapshot)
                .where(OddsSnapshot.fixture_id == fixture_id)
                .order_by(desc(OddsSnapshot.captured_at))
                .limit(30)
            )
        )
        .scalars()
        .all()
    )
    result = (
        await db.execute(select(Result).where(Result.fixture_id == fixture_id))
    ).scalar_one_or_none()
    latest_prediction = predictions[0] if predictions else None
    home_team_zh, away_team_zh = await team_display_pair(
        db, match.home_team_name, match.away_team_name
    )
    market_cards = build_market_cards(latest_prediction, candidates, snapshots)
    analysis_report = build_report_template(
        home_team_zh=home_team_zh or match.home_team_name or "",
        away_team_zh=away_team_zh or match.away_team_name or "",
        home_team=match.home_team_name or "",
        away_team=match.away_team_name or "",
        league=match.league_name,
        fixture_id=fixture_id,
        prediction=latest_prediction,
        market_cards=market_cards,
    )
    return {
        "fixture_id": fixture_id,
        "home_team": match.home_team_name,
        "away_team": match.away_team_name,
        "home_team_zh": home_team_zh,
        "away_team_zh": away_team_zh,
        "league": match.league_name,
        "kickoff": match.match_date.isoformat() if match.match_date else None,
        "status": match.status,
        "market_cards": market_cards,
        "analysis_report": analysis_report,
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
                "best_market": item.best_market,
                "best_odds": item.best_odds,
                "best_ev": item.best_ev,
                "best_kelly": item.best_kelly,
                "best_edge": item.best_edge,
                "home_win_prob": item.home_win_prob,
                "draw_prob": item.draw_prob,
                "away_win_prob": item.away_win_prob,
                "value_score": item.value_score,
                "risk": item.risk,
                "settled_status": item.settled_status,
                "profit_units": item.profit_units,
                "settlement_note": item.settlement_note,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "report_text": item.report_text,
            }
            for item in predictions
        ],
        "value_candidates": [
            {
                "market": item.market,
                "pick": item.pick,
                "display_pick": item.display_pick,
                "line": item.line,
                "odds": item.odds,
                "market_prob": item.market_prob,
                "prob": item.prob,
                "ev": item.ev,
                "kelly": item.kelly,
                "edge": item.edge,
                "bookmaker_count": item.bookmaker_count,
                "consensus_score": item.consensus_score,
                "disagreement_index": item.disagreement_index,
                "data_quality_score": item.data_quality_score,
                "risk": item.risk,
                "value_score": item.value_score,
                "selected": item.selected,
                "settled_status": item.settled_status,
                "profit_units": item.profit_units,
                "settlement_note": item.settlement_note,
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
                "ah_home_odds": item.ah_home_odds,
                "ah_away_odds": item.ah_away_odds,
                "ou_line": item.ou_line,
                "over_odds": item.over_odds,
                "under_odds": item.under_odds,
                "snapshot_type": item.snapshot_type,
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
