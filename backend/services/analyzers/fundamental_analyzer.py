"""
基本面分析器 — 排名 / 主客战绩 / 近况 / 交锋

数据来源：API-Football /standings + /teams/statistics + /fixtures/headtohead
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)


def analyze(
    api: ApiFootballClient,
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """
    获取基本面数据。

    Args:
        api: API-Football 客户端
        fixture: API-Football fixture 原始数据

    Returns:
        {
            "standings": {home: {...}, away: {...}},
            "home_record": {...},
            "away_record": {...},
            "form": {home: {...}, away: {...}},
            "h2h": [{...}, ...],
            "h2h_summary": {"home_wins": N, "draws": N, "away_wins": N},
        }
    """
    league = fixture.get("league", {})
    teams = fixture.get("teams", {})
    season = league.get("season") or datetime.now(timezone.utc).year
    league_id = league.get("id")
    home_team = teams.get("home", {})
    away_team = teams.get("away", {})
    home_id = home_team.get("id")
    away_id = away_team.get("id")

    result: dict[str, Any] = {
        "standings": {},
        "home_record": {},
        "away_record": {},
        "form": {},
        "h2h": [],
        "h2h_summary": {"home_wins": 0, "draws": 0, "away_wins": 0},
    }

    # 1. 积分榜
    if league_id:
        standings = _fetch_standings(api, league_id, season)
        result["standings"] = _extract_standings(standings, home_id, away_id)

    # 2. 球队赛季统计（主客场拆分）
    if home_id:
        result["home_record"] = _fetch_team_stats(api, league_id, home_id, season)
    if away_id:
        result["away_record"] = _fetch_team_stats(api, league_id, away_id, season)

    # 3. 近期状态（近5/10场）
    if home_id:
        result["form"]["home"] = _fetch_recent_form(api, home_id)
    if away_id:
        result["form"]["away"] = _fetch_recent_form(api, away_id)

    # 4. 历史交锋（近6场）
    if home_id and away_id:
        h2h = _fetch_h2h(api, home_id, away_id, limit=6)
        result["h2h"] = h2h
        result["h2h_summary"] = _summarize_h2h(h2h, home_id)

    return result


def _fetch_standings(api: ApiFootballClient, league_id: int, season: int) -> list[dict]:
    data = api.get("/standings", {"league": league_id, "season": season})
    resp = data.get("response", [])
    if not resp:
        return []
    return resp[0].get("league", {}).get("standings", [[]])[0]


def _extract_standings(
    standings: list[dict], home_id: int | None, away_id: int | None
) -> dict[str, dict]:
    result = {}
    for entry in standings:
        team = entry.get("team", {})
        tid = team.get("id")
        all_stats = entry.get("all", {})
        if tid == home_id:
            result["home"] = _parse_standings_entry(entry)
        elif tid == away_id:
            result["away"] = _parse_standings_entry(entry)
    return result


def _parse_standings_entry(entry: dict) -> dict:
    team = entry.get("team", {})
    all_stats = entry.get("all", {})
    home_stats = entry.get("home", {})
    away_stats = entry.get("away", {})
    goals = all_stats.get("goals", {})
    return {
        "rank": entry.get("rank", 0),
        "team_name": team.get("name", ""),
        "points": entry.get("points", 0),
        "played": all_stats.get("played", 0),
        "win": all_stats.get("win", 0),
        "draw": all_stats.get("draw", 0),
        "lose": all_stats.get("lose", 0),
        "goals_for": goals.get("for", 0),
        "goals_against": goals.get("against", 0),
        "goal_diff": (goals.get("for", 0) or 0) - (goals.get("against", 0) or 0),
        "form": entry.get("form", ""),
        "home_record": _record_str(home_stats),
        "away_record": _record_str(away_stats),
        "home_goals_for": home_stats.get("goals", {}).get("for", 0),
        "home_goals_against": home_stats.get("goals", {}).get("against", 0),
        "away_goals_for": away_stats.get("goals", {}).get("for", 0),
        "away_goals_against": away_stats.get("goals", {}).get("against", 0),
    }


def _record_str(stats: dict) -> str:
    w = stats.get("win", 0)
    d = stats.get("draw", 0)
    l = stats.get("lose", 0)
    return f"{w}胜{d}平{l}负"


def _fetch_team_stats(
    api: ApiFootballClient, league_id: int | None, team_id: int, season: int
) -> dict:
    if not league_id:
        return {}
    data = api.get(
        "/teams/statistics",
        {"league": league_id, "team": team_id, "season": season},
    )
    resp = data.get("response", {})
    if not resp:
        return {}

    fixtures = resp.get("fixtures", {})
    goals = resp.get("goals", {})
    played = fixtures.get("played", {}).get("total", 1) or 1

    return {
        "team_name": resp.get("team", {}).get("name", ""),
        "matches_played": played,
        "wins": fixtures.get("wins", {}).get("total", 0),
        "draws": fixtures.get("draws", {}).get("total", 0),
        "losses": fixtures.get("loses", {}).get("total", 0),
        "goals_for_avg": (goals.get("for", {}).get("total", {}).get("total", 0) or 0) / played,
        "goals_against_avg": (goals.get("against", {}).get("total", {}).get("total", 0) or 0) / played,
        "avg_shots": (resp.get("shots", {}).get("total", 0) or 0) / played if "shots" in resp else 0,
        "avg_possession": _parse_pct(resp.get("possession", {}).get("average", "0%")),
        "form": resp.get("form", ""),
    }


def _parse_pct(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        return float(str(s).rstrip("%")) / 100
    except (ValueError, TypeError):
        return 0.0


def _fetch_recent_form(api: ApiFootballClient, team_id: int, limit: int = 10) -> dict:
    """获取球队最近 N 场比赛"""
    data = api.get(
        "/fixtures",
        {"team": team_id, "last": limit, "timezone": "UTC"},
    )
    matches = data.get("response", [])
    wins = draws = losses = 0
    goals_for = goals_against = 0
    clean_sheets = 0
    form_str = ""

    for m in matches:
        teams = m.get("teams", {})
        goals = m.get("goals", {})
        is_home = teams.get("home", {}).get("id") == team_id
        gf = goals.get("home", 0) if is_home else goals.get("away", 0)
        ga = goals.get("away", 0) if is_home else goals.get("home", 0)

        if gf is None or ga is None:
            continue

        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
            form_str = "W" + form_str
        elif gf == ga:
            draws += 1
            form_str = "D" + form_str
        else:
            losses += 1
            form_str = "L" + form_str
        if ga == 0:
            clean_sheets += 1

    total = wins + draws + losses
    return {
        "form": form_str[:10],
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for_avg": round(goals_for / total, 2) if total else 0,
        "goals_against_avg": round(goals_against / total, 2) if total else 0,
        "clean_sheet_rate": round(clean_sheets / total, 2) if total else 0,
        "form_score": round((wins * 3 + draws) / (total * 3) if total else 0.5, 2),
    }


def _fetch_h2h(api: ApiFootballClient, team1: int, team2: int, limit: int = 6) -> list[dict]:
    data = api.get("/fixtures/headtohead", {"h2h": f"{team1}-{team2}", "last": limit})
    matches = data.get("response", [])
    result = []
    for m in matches:
        fixture = m.get("fixture", {})
        teams = m.get("teams", {})
        goals = m.get("goals", {})
        league = m.get("league", {})
        result.append(
            {
                "date": fixture.get("date", ""),
                "league": league.get("name", ""),
                "home_team": teams.get("home", {}).get("name", ""),
                "away_team": teams.get("away", {}).get("name", ""),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
            }
        )
    return result


def _summarize_h2h(h2h: list[dict], home_team_id: int) -> dict:
    home_wins = draws = away_wins = 0
    for m in h2h:
        hg = m.get("home_goals")
        ag = m.get("away_goals")
        if hg is None or ag is None:
            continue
        if hg > ag:
            home_wins += 1
        elif hg == ag:
            draws += 1
        else:
            away_wins += 1
    return {"home_wins": home_wins, "draws": draws, "away_wins": away_wins}
