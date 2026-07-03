"""
数据服务 — 联赛、球队、比赛数据查询
"""
from __future__ import annotations
import logging
from models.league import League
from models.match import Match
from models.team import Team
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

class DataService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_leagues(self) -> list[dict]:
        rows = (await self.db.execute(select(League).order_by(League.name))).scalars().all()
        return [{"id": r.id, "name": r.name, "country": r.country, "tier": r.tier, "api_source": r.api_source, "external_id": r.external_id} for r in rows]

    async def get_standings(self, league_id: int) -> list[dict]:
        from services.telegram_mvp.api_football import ApiFootballClient
        api = ApiFootballClient()
        data = api.get("/standings", {"league": league_id, "season": 2026})
        resp = data.get("response", [])
        if not resp:
            return []
        standings = resp[0].get("league", {}).get("standings", [[]])[0]
        return [{"rank": e.get("rank"), "team_name": e.get("team",{}).get("name"), "points": e.get("points"), "played": e.get("all",{}).get("played"), "win": e.get("all",{}).get("win"), "draw": e.get("all",{}).get("draw"), "lose": e.get("all",{}).get("lose"), "goals_for": e.get("all",{}).get("goals",{}).get("for"), "goals_against": e.get("all",{}).get("goals",{}).get("against"), "form": e.get("form","")} for e in standings]

    async def get_teams(self, league_id: int) -> list[dict]:
        rows = (await self.db.execute(select(Team).where(Team.league_id == league_id).order_by(Team.name))).scalars().all()
        return [{"id": r.id, "name": r.name, "country": r.country, "external_id": r.external_id} for r in rows]

    async def get_matches(self, league_id: int, date_from: str = None, date_to: str = None) -> list[dict]:
        stmt = select(Match).where(Match.league_id == league_id)
        if date_from:
            from datetime import datetime
            stmt = stmt.where(Match.match_date >= datetime.fromisoformat(date_from))
        if date_to:
            from datetime import datetime
            stmt = stmt.where(Match.match_date <= datetime.fromisoformat(date_to))
        stmt = stmt.order_by(Match.match_date)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [{"id": r.id, "fixture_id": r.api_fixture_id, "home_team": r.home_team_name, "away_team": r.away_team_name, "match_date": r.match_date.isoformat() if r.match_date else None, "status": r.status, "home_score": r.home_score, "away_score": r.away_score} for r in rows]
