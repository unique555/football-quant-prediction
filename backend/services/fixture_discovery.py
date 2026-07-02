"""
比赛发现引擎 — 自动扫描全球赛程 → 黑名单过滤 → 全量入库

策略：不做白名单限制，API 有数据的比赛全跑。
  - 排除黑名单：友谊赛、青年赛、女足（可选）、5人制等无分析价值的比赛
  - 其余所有联赛全部入库
  - auto_analyze 阶段自然过滤：无赔率数据的比赛自动跳过
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from models.league import League
from models.match import Match
from models.team import Team
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)

# ============================================================
# 黑名单 — 这些类型的比赛不分析（无赔率/无统计/无分析价值）
# ============================================================

EXCLUDED_LEAGUE_NAMES = {
    # 友谊赛
    "Friendlies Clubs",
    "Friendlies Women",
    "Friendlies Internationals",
    # 青年赛
    "Youth Championship",
    "U19 Championship",
    "U17 Championship",
    "Reserve League",
    "Youth League",
    # 女足（可选，取消注释则排除）
    # "NWSL Women",
    # "Women's Super League",
    # 五人制/沙滩
    "Futsal",
    "Beach Soccer",
}

# 联赛名称包含这些关键词也排除
EXCLUDED_KEYWORDS = ["U15", "U16", "U17", "U18", "U19", "U20", "U21", "U23", "Youth", "Reserve", "Futsal", "Beach", "Women"]

# 只分析未开赛的比赛状态
SCHEDULED_STATUSES = {"NS", "TBD", "PST"}


def _is_excluded(league_name: str) -> bool:
    """判断联赛是否在黑名单中"""
    if not league_name:
        return True
    if league_name in EXCLUDED_LEAGUE_NAMES:
        return True
    name_lower = league_name.lower()
    for kw in EXCLUDED_KEYWORDS:
        if kw.lower() in name_lower:
            return True
    return False


# ============================================================
# 热门联赛标记（不是过滤，只是分档标记，全部入库）
# ============================================================

HOT_LEAGUE_IDS = {
    39, 140, 135, 78, 61,   # 五大联赛
    2, 3, 848,              # 欧战
    40, 141, 136, 79, 62,   # 二级联赛
    88, 94,                 # 荷甲葡超
    71, 253, 98,            # 巴甲MLS日职
    292, 293,               # K联赛
    1,                      # 世界杯
}


class FixtureDiscovery:
    """比赛发现引擎 — 全量扫描、黑名单过滤、入库"""

    def __init__(self, api_client: ApiFootballClient | None = None):
        self.api = api_client or ApiFootballClient()

    async def discover(
        self,
        session: AsyncSession,
        days_ahead: int = 7,
    ) -> dict[str, int]:
        """
        扫描未来 N 天的赛程，黑名单过滤后全量入库。

        Returns:
            {"scanned": 总扫描数, "excluded": 黑名单排除, "new": 新入库, "skipped": 已在库}
        """
        stats = {"scanned": 0, "excluded": 0, "new": 0, "skipped": 0}
        now = datetime.now(timezone.utc)

        for delta in range(days_ahead + 1):
            date_str = (now + timedelta(days=delta)).date().isoformat()
            fixtures = self._fetch_fixtures_by_date(date_str)
            stats["scanned"] += len(fixtures)

            for fixture in fixtures:
                parsed = self._parse_fixture(fixture)
                if not parsed:
                    continue

                # 黑名单过滤
                if _is_excluded(parsed["league_name"]):
                    stats["excluded"] += 1
                    continue

                # 去重：检查 fixture_id 是否已入库
                existing = await session.execute(
                    select(Match).where(Match.api_fixture_id == parsed["api_fixture_id"])
                )
                if existing.scalar_one_or_none():
                    stats["skipped"] += 1
                    continue

                # 入库 League（upsert）
                await self._upsert_league(session, parsed)
                # 入库 Teams
                await self._upsert_teams(session, parsed)
                # 入库 Match
                session.add(parsed["match_obj"])
                stats["new"] += 1

        await session.commit()
        logger.info(
            "fixture_discovery: scanned=%d excluded=%d new=%d skipped=%d",
            stats["scanned"],
            stats["excluded"],
            stats["new"],
            stats["skipped"],
        )
        return stats

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _fetch_fixtures_by_date(self, date_str: str) -> list[dict[str, Any]]:
        """从 API-Football 拉取某日全部赛程"""
        data = self.api.get("/fixtures", {"date": date_str, "timezone": "UTC"})
        return data.get("response", [])

    def _parse_fixture(self, fixture: dict[str, Any]) -> dict[str, Any] | None:
        """解析 API-Football fixture，返回结构化数据"""
        f = fixture.get("fixture", {})
        league = fixture.get("league", {})
        teams = fixture.get("teams", {})

        fixture_id = f.get("id")
        league_id = league.get("id")
        status_short = f.get("status", {}).get("short", "NS")

        if not fixture_id or not league_id:
            return None

        # 只要未开赛的比赛
        if status_short not in SCHEDULED_STATUSES:
            return None

        home_team = teams.get("home", {})
        away_team = teams.get("away", {})

        match_date_str = f.get("date", "")
        try:
            match_date = datetime.fromisoformat(
                match_date_str.replace("Z", "+00:00")
            ).replace(tzinfo=None)
        except (ValueError, TypeError):
            return None

        league_name = league.get("name", "")
        league_country = league.get("country", "")
        is_hot = league_id in HOT_LEAGUE_IDS
        tier = 1 if is_hot else 2

        match_obj = Match(
            api_fixture_id=fixture_id,
            api_league_id=league_id,
            season=league.get("season"),
            home_team_name=home_team.get("name", ""),
            away_team_name=away_team.get("name", ""),
            league_name=league_name,
            match_date=match_date,
            status="scheduled",
            venue=f.get("venue", {}).get("name", ""),
            external_id=str(fixture_id),
        )

        return {
            "api_fixture_id": fixture_id,
            "api_league_id": league_id,
            "league_name": league_name,
            "league_country": league_country,
            "league_tier": tier,
            "season": league.get("season"),
            "home_team_id": home_team.get("id"),
            "home_team_name": home_team.get("name", ""),
            "home_team_country": home_team.get("country", ""),
            "away_team_id": away_team.get("id"),
            "away_team_name": away_team.get("name", ""),
            "away_team_country": away_team.get("country", ""),
            "match_date": match_date,
            "match_obj": match_obj,
            "round_name": league.get("round", ""),
        }

    async def _upsert_league(self, session: AsyncSession, parsed: dict[str, Any]) -> None:
        """upsert 联赛记录"""
        stmt = pg_insert(League).values(
            name=parsed["league_name"],
            country=parsed["league_country"],
            tier=parsed["league_tier"],
            api_source="api-football",
            external_id=str(parsed["api_league_id"]),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["external_id"],
            set_={
                "name": stmt.excluded.name,
                "country": stmt.excluded.country,
                "tier": stmt.excluded.tier,
            },
        )
        await session.execute(stmt)

    async def _upsert_teams(self, session: AsyncSession, parsed: dict[str, Any]) -> None:
        """upsert 球队记录（主队 + 客队）"""
        for team_data in [
            {
                "external_id": str(parsed["home_team_id"]) if parsed["home_team_id"] else None,
                "name": parsed["home_team_name"],
                "country": parsed["home_team_country"],
            },
            {
                "external_id": str(parsed["away_team_id"]) if parsed["away_team_id"] else None,
                "name": parsed["away_team_name"],
                "country": parsed["away_team_country"],
            },
        ]:
            if not team_data["name"]:
                continue
            stmt = pg_insert(Team).values(
                name=team_data["name"],
                country=team_data["country"],
                external_id=team_data["external_id"],
            )
            stmt = stmt.on_conflict_do_nothing(index_elements=["external_id"])
            await session.execute(stmt)
