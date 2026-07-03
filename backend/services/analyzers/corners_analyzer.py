"""
角球分析器 — 期望角球数 / 角球盘口 / edge

数据来源：API-Football /fixtures/statistics（角球统计），
        若 API 不提供角球统计，则从 fundamental_data 的进球+射门数据推断。
盘口从 odds_aggregates["corners"] 提取（若存在）。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)

# 拉取近期比赛列表的场数
_RECENT_FIXTURES_LIMIT = 10
# 实际拉取 statistics 的场数上限（控制 API 调用量）
_STATS_FETCH_LIMIT = 3
# 已完赛的状态码
_FINISHED_STATUS = {"FT", "AET", "PEN"}


def analyze(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    fundamental_data: dict[str, Any],
    odds_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    角球分析主入口。

    Args:
        api: API-Football 客户端
        fixture: API-Football fixture 原始数据
        fundamental_data: fundamental_analyzer.analyze 的返回值
        odds_aggregates: dict，键为市场名，值为 MarketAggregate 或 None

    Returns:
        {
            "expected_corners": {"home": float, "away": float, "total": float},
            "line": float|None,
            "over_odds": float|None,
            "under_odds": float|None,
            "edge": float|None,
            "description": str,
        }
        数据不足时返回空结构。
    """
    odds_aggregates = odds_aggregates or {}
    fundamental_data = fundamental_data or {}
    teams = fixture.get("teams", {}) or {}
    home_id = (teams.get("home", {}) or {}).get("id")
    away_id = (teams.get("away", {}) or {}).get("id")

    home_record = fundamental_data.get("home_record", {}) or {}
    away_record = fundamental_data.get("away_record", {}) or {}

    # 优先从 API 获取角球统计
    home_corners = _fetch_team_avg_corners(api, home_id)
    away_corners = _fetch_team_avg_corners(api, away_id)

    description_parts: list[str] = []

    if home_corners is not None and away_corners is not None:
        home_avg = home_corners
        away_avg = away_corners
        description_parts.append("基于近况角球统计")
    elif home_corners is not None:
        home_avg = home_corners
        away_avg = _infer_corners(away_record)
        description_parts.append("主队基于角球统计，客队基于进球射门推断")
    elif away_corners is not None:
        home_avg = _infer_corners(home_record)
        away_avg = away_corners
        description_parts.append("主队基于进球射门推断，客队基于角球统计")
    else:
        home_avg = _infer_corners(home_record)
        away_avg = _infer_corners(away_record)
        description_parts.append("基于进球射门推断（无角球统计数据）")

    total_corners = home_avg + away_avg

    # 从赔率中提取角球盘口
    line, over_odds, under_odds = _extract_corners_odds(odds_aggregates)

    # 计算 edge
    edge = None
    if line is not None and over_odds:
        over_prob = _corners_over_prob(total_corners, line)
        market_prob = 1.0 / over_odds
        edge = round(over_prob - market_prob, 4)

    # 描述文本
    if total_corners > 0:
        description_parts.append(
            f"主队预期角球 {home_avg:.1f}，客队预期角球 {away_avg:.1f}，合计 {total_corners:.1f}"
        )
    description = "；".join(description_parts) + "。"

    return {
        "expected_corners": {
            "home": round(home_avg, 2),
            "away": round(away_avg, 2),
            "total": round(total_corners, 2),
        },
        "line": line,
        "over_odds": over_odds,
        "under_odds": under_odds,
        "edge": edge,
        "description": description,
    }


# ---------------------------------------------------------------------------
# API 角球统计获取
# ---------------------------------------------------------------------------

def _fetch_team_avg_corners(api: ApiFootballClient, team_id: int | None) -> float | None:
    """
    拉取球队近 N 场已完赛比赛的角球统计，返回场均角球数。
    为控制 API 调用量，最多查询 _STATS_FETCH_LIMIT 场的 statistics。
    """
    if not team_id:
        return None

    try:
        data = api.get(
            "/fixtures",
            {"team": team_id, "last": _RECENT_FIXTURES_LIMIT, "timezone": "UTC"},
        )
        fixtures = data.get("response", []) or []
    except Exception as exc:  # noqa: BLE001 — 容错
        logger.warning("corners_analyzer: 拉取球队比赛失败 team=%s err=%s", team_id, exc)
        return None

    corners_list: list[int] = []
    fetched = 0
    for m in fixtures:
        if fetched >= _STATS_FETCH_LIMIT:
            break
        fixture_info = m.get("fixture", {}) or {}
        status = (fixture_info.get("status", {}) or {}).get("short", "")
        if status not in _FINISHED_STATUS:
            continue
        fid = fixture_info.get("id")
        if not fid:
            continue

        corners = _fetch_fixture_corners(api, fid, team_id)
        if corners is not None:
            corners_list.append(corners)
        fetched += 1

    if not corners_list:
        return None
    return sum(corners_list) / len(corners_list)


def _fetch_fixture_corners(
    api: ApiFootballClient, fixture_id: int, team_id: int
) -> int | None:
    """从 /fixtures/statistics 提取指定球队的角球数。"""
    try:
        data = api.get("/fixtures/statistics", {"fixture": fixture_id})
        stats = data.get("response", []) or []
    except Exception as exc:  # noqa: BLE001 — 容错
        logger.warning(
            "corners_analyzer: 拉取统计失败 fixture=%s err=%s", fixture_id, exc
        )
        return None

    return _extract_corners(stats, team_id)


def _extract_corners(stats_response: list[dict], team_id: int) -> int | None:
    """
    从 /fixtures/statistics 响应中提取指定球队的角球数。
    统计类型名含 "Corner"（如 "Corner Kicks"）。
    """
    for entry in stats_response:
        team = entry.get("team", {}) or {}
        if team.get("id") != team_id:
            continue
        for stat in entry.get("statistics", []) or []:
            stat_type = (stat.get("type") or "").lower()
            if "corner" not in stat_type:
                continue
            value = stat.get("value")
            if value is None:
                continue
            try:
                return int(str(value).strip())
            except (ValueError, TypeError):
                return None
    return None


# ---------------------------------------------------------------------------
# 角球推断（无统计数据时的回退方案）
# ---------------------------------------------------------------------------

def _infer_corners(record: dict[str, Any]) -> float:
    """
    用进球数 + 射门数推断角球数。

    进攻型球队角球更多：场均进球高、射门多 → 角球多。
    基础值 4.5 + 进攻加成 + 防守被压制加成。
    """
    gf = _safe_float(record.get("goals_for_avg"))
    ga = _safe_float(record.get("goals_against_avg"))
    shots = _safe_float(record.get("avg_shots"))

    base = 4.5
    attack_bonus = gf * 0.6 + max(0.0, shots - 10.0) * 0.15
    defense_bonus = ga * 0.2  # 被压制时防守反击也产生角球

    return round(base + attack_bonus + defense_bonus, 2)


# ---------------------------------------------------------------------------
# 角球盘口与 edge
# ---------------------------------------------------------------------------

def _extract_corners_odds(
    odds_aggregates: dict[str, Any]
) -> tuple[float | None, float | None, float | None]:
    """从 odds_aggregates 提取角球盘口（line / over / under）。"""
    corners_agg = odds_aggregates.get("corners")
    if not corners_agg:
        return None, None, None
    avg_odds = corners_agg.avg_odds or {}
    line = avg_odds.get("line")
    over = avg_odds.get("over")
    under = avg_odds.get("under")
    return line, over, under


def _corners_over_prob(expected_total: float, line: float) -> float:
    """
    用正态近似估算角球 over 概率。
    角球近似服从正态分布，方差约等于均值。
    加入连续性修正：P(X > line) ≈ 1 - Φ((line + 0.5 - μ) / σ)。
    """
    if expected_total <= 0:
        return 0.0
    mean = expected_total
    std = math.sqrt(expected_total)
    if std <= 0:
        return 0.5
    z = (line + 0.5 - mean) / std
    return 1.0 - _normal_cdf(z)


def _normal_cdf(z: float) -> float:
    """标准正态分布 CDF，用 math.erf 实现。"""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float:
    try:
        f = float(value)
        return f if f > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# 空结构
# ---------------------------------------------------------------------------

def _empty_result() -> dict[str, Any]:
    return {
        "expected_corners": {"home": 0.0, "away": 0.0, "total": 0.0},
        "line": None,
        "over_odds": None,
        "under_odds": None,
        "edge": None,
        "description": "",
    }
