"""Fixture resolution and candidate ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from services.telegram_mvp.names import MatchQuery, team_similarity

SHANGHAI_TZ = timezone(timedelta(hours=8))
FINISHED_STATUSES = {"FT", "AET", "PEN", "CANC", "PST", "ABD", "AWD", "WO"}


@dataclass(frozen=True)
class FixtureCandidate:
    fixture_id: int
    home_team: str
    away_team: str
    league: str
    season: int | None
    kickoff: str
    status: str
    score: float
    raw: dict[str, Any]


def parse_fixture_datetime(item: dict[str, Any]) -> datetime | None:
    date_text = item.get("fixture", {}).get("date") or ""
    if not date_text:
        return None
    try:
        return datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone(SHANGHAI_TZ)
    except ValueError:
        return None


def fixture_match_score(item: dict[str, Any], query: MatchQuery) -> float:
    teams = item.get("teams", {})
    home_name = teams.get("home", {}).get("name", "")
    away_name = teams.get("away", {}).get("name", "")
    direct = (team_similarity(query.home, home_name) + team_similarity(query.away, away_name)) / 2
    reverse = (team_similarity(query.home, away_name) + team_similarity(query.away, home_name)) / 2
    return max(direct, reverse)


def rank_fixture_candidates(fixtures: list[dict[str, Any]], query: MatchQuery) -> list[FixtureCandidate]:
    now = datetime.now(SHANGHAI_TZ)
    ranked: list[FixtureCandidate] = []

    for item in fixtures:
        fixture = item.get("fixture", {})
        fixture_id = fixture.get("id")
        if not fixture_id:
            continue
        teams = item.get("teams", {})
        league = item.get("league", {})
        kickoff_dt = parse_fixture_datetime(item)
        status = fixture.get("status", {}).get("short", "")
        score = fixture_match_score(item, query)
        if score < 0.72:
            continue
        if kickoff_dt:
            days = abs((kickoff_dt - now).total_seconds()) / 86400
            score -= min(days, 14) * 0.01
            if status in FINISHED_STATUSES:
                score -= 0.08
        ranked.append(
            FixtureCandidate(
                fixture_id=int(fixture_id),
                home_team=teams.get("home", {}).get("name", ""),
                away_team=teams.get("away", {}).get("name", ""),
                league=league.get("name", ""),
                season=league.get("season"),
                kickoff=fixture.get("date", ""),
                status=status,
                score=round(score, 4),
                raw=item,
            )
        )

    return sorted(ranked, key=lambda c: c.score, reverse=True)


def should_return_candidates(candidates: list[FixtureCandidate]) -> bool:
    if len(candidates) <= 1:
        return False
    top, second = candidates[0], candidates[1]
    return top.score < 0.93 or second.score >= top.score - 0.04


def format_candidate_list(candidates: list[FixtureCandidate]) -> str:
    lines = ["找到多个相似比赛：", ""]
    for idx, item in enumerate(candidates[:5], 1):
        kickoff = item.kickoff[:16].replace("T", " ")
        lines.append(f"{idx}. {item.home_team} vs {item.away_team} - {kickoff} - {item.league}")
    lines.append("")
    lines.append("请回复编号选择。")
    return "\n".join(lines)
