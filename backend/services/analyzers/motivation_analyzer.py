"""
战意与剧本分析器 — 球队比赛动机 / 赛程密度 / 伤病停赛 / 客场旅程 / 剧本推断

数据来源：API-Football /fixtures（赛程密度）、/injuries（伤病）、/players（停赛黄牌）
依赖 fundamental_analyzer 提供的积分榜数据（rank / points / played 等）。
全部基于规则推断，不调用 LLM。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)

# 战意等级标签
_MOTIVATION_EXTREME = "🔥🔥🔥极强"
_MOTIVATION_STRONG = "🔥🔥强"
_MOTIVATION_MEDIUM = "🔥中"
_MOTIVATION_LOW = "低"

# 联赛段位阈值（按典型 20 队联赛估算，可被覆盖）
_TOP_ZONE = 1            # 榜首区
_CHAMPIONS_LEAGUE_SPOTS = 4   # 欧冠区末位
_EUROPA_LEAGUE_SPOTS = 6      # 欧联区末位
_RELEGATION_THRESHOLD = 17    # 降级区起始名次（17~20 为降级区）


def analyze(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    fundamental_data: dict[str, Any],
) -> dict[str, Any]:
    """
    战意与剧本分析主入口。

    Args:
        api: API-Football 客户端，提供 .get(path, params) 方法
        fixture: API-Football fixture 原始数据
        fundamental_data: fundamental_analyzer.analyze 的返回值，
            预期含 standings[home/away] = {rank, points, played, ...}

    Returns:
        {
            "motivation": {
                "home": {"level": str, "reason": str},
                "away": {"level": str, "reason": str},
            },
            "script_factors": [
                {"factor": str, "impact": str, "weight": str}, ...
            ],
            "scenarios": [
                {"name": str, "probability": float, "description": str}, ...
            ],
        }
        数据不足时返回合理默认值，不抛异常。
    """
    teams = fixture.get("teams", {})
    home_team = teams.get("home", {}) or {}
    away_team = teams.get("away", {}) or {}
    home_id = home_team.get("id")
    away_id = away_team.get("id")
    fixture_date_str = (fixture.get("fixture", {}) or {}).get("date", "")

    standings = fundamental_data.get("standings", {}) if fundamental_data else {}
    home_std = standings.get("home", {}) or {}
    away_std = standings.get("away", {}) or {}

    # 1. 战意判断
    home_motivation = _assess_motivation(home_std, "home")
    away_motivation = _assess_motivation(away_std, "away")

    # 2. 剧本因子（赛程密度 / 伤病 / 停赛 / 客场旅程）
    script_factors: list[dict[str, str]] = []
    try:
        script_factors.extend(_fixture_density_factors(api, fixture, home_id, away_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("赛程密度分析失败: %s", exc)
    try:
        script_factors.extend(_injury_factors(api, fixture, home_id, away_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("伤病分析失败: %s", exc)
    try:
        script_factors.extend(_suspension_factors(api, fixture, home_id, away_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("停赛分析失败: %s", exc)
    try:
        script_factors.append(_travel_factor(fixture, away_team))
    except Exception as exc:  # noqa: BLE001
        logger.warning("客场旅程分析失败: %s", exc)

    if not script_factors:
        script_factors = [
            {"factor": "无可用剧本因子", "impact": "中性", "weight": "低"},
        ]

    # 3. 三种可能剧本
    scenarios = _build_scenarios(
        home_std, away_std, home_motivation, away_motivation, fundamental_data
    )

    return {
        "motivation": {"home": home_motivation, "away": away_motivation},
        "script_factors": script_factors,
        "scenarios": scenarios,
    }


# ----------------------------------------------------------------------------
# 战意评估
# ----------------------------------------------------------------------------

def _assess_motivation(standing: dict[str, Any], side: str) -> dict[str, str]:
    """
    根据积分榜位置推断战意等级。

    规则：
      - 距榜首 ≤ 3 分：争冠极强
      - 距欧战区末位 ≤ 3 分：争四强（若已落入争冠区则保持极强）
      - 距降级区起点 ≤ 3 分：保级强（若已落入降级区则保级极强）
      - 联赛中段无压力：中
      - 已无目标（极端靠后且远离降级）：低
    """
    rank = standing.get("rank") or 0
    points = standing.get("points") or 0
    played = standing.get("played") or 0
    team_name = standing.get("team_name", "本队")

    # 数据不足，返回默认中等战意
    if not rank or not played:
        return {
            "level": _MOTIVATION_MEDIUM,
            "reason": f"{team_name}积分榜数据不足，按常规战意估算",
        }

    # 榜首：争冠
    if rank == 1:
        return {
            "level": _MOTIVATION_EXTREME,
            "reason": f"{team_name}位列榜首({points}分)，每场必争以捍卫王座",
        }

    # 距榜首 ≤ 3 分：争冠极强
    gap_to_top = points - _TOP_ZONE  # 不知榜首分，需用 rank 推断
    # 这里没有完整积分榜，按名次推断阈值
    if rank <= 3:
        return {
            "level": _MOTIVATION_EXTREME,
            "reason": f"{team_name}排名{rank}({points}分)，处于争冠集团，战意极强",
        }

    # 争四区（4~6名）：距欧冠/欧联区边缘
    if _CHAMPIONS_LEAGUE_SPOTS < rank <= _EUROPA_LEAGUE_SPOTS:
        return {
            "level": _MOTIVATION_STRONG,
            "reason": f"{team_name}排名{rank}({points}分)，争夺欧战席位，战意强",
        }
    if rank == _CHAMPIONS_LEAGUE_SPOTS:
        return {
            "level": _MOTIVATION_STRONG,
            "reason": f"{team_name}排名{rank}({points}分)，欧冠区边缘，不容有失",
        }

    # 降级区：已落入或濒临
    if rank >= _RELEGATION_THRESHOLD:
        return {
            "level": _MOTIVATION_EXTREME,
            "reason": f"{team_name}排名{rank}({points}分)，深陷降级区，保级生死战",
        }
    if rank >= _RELEGATION_THRESHOLD - 2:
        return {
            "level": _MOTIVATION_STRONG,
            "reason": f"{team_name}排名{rank}({points}分)，逼近降级区，抢分压力大",
        }

    # 中段（7~14名）：通常无压力
    if 7 <= rank <= 14:
        # 赛季末段若仍处中段且远离两端，则战意低
        if played >= 30:
            return {
                "level": _MOTIVATION_LOW,
                "reason": f"{team_name}排名{rank}({points}分)，赛季末段已无目标，战意低",
            }
        return {
            "level": _MOTIVATION_MEDIUM,
            "reason": f"{team_name}排名{rank}({points}分)，联赛中段，战意一般",
        }

    # 默认中等
    return {
        "level": _MOTIVATION_MEDIUM,
        "reason": f"{team_name}排名{rank}({points}分)，按常规战意估算",
    }


# ----------------------------------------------------------------------------
# 剧本因子
# ----------------------------------------------------------------------------

def _parse_fixture_date(date_str: str) -> datetime | None:
    """解析 API-Football 的 ISO 时间字符串。"""
    if not date_str:
        return None
    try:
        # 形如 2024-09-21T14:00:00+00:00
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _fixture_density_factors(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    home_id: int | None,
    away_id: int | None,
) -> list[dict[str, str]]:
    """
    通过 /fixtures?team=X&from=...&to=... 查近 7 天比赛数，判断赛程密度。
    每支球队单独返回一个因子项。
    """
    fixture_info = fixture.get("fixture", {}) or {}
    match_date = _parse_fixture_date(fixture_info.get("date", ""))
    if not match_date:
        match_date = datetime.now(timezone.utc)

    date_from = (match_date - timedelta(days=7)).date().isoformat()
    date_to = match_date.date().isoformat()

    factors: list[dict[str, str]] = []
    for side, team_id, label in (
        ("home", home_id, "主队"),
        ("away", away_id, "客队"),
    ):
        if not team_id:
            continue
        try:
            data = api.get(
                "/fixtures",
                {
                    "team": team_id,
                    "from": date_from,
                    "to": date_to,
                    "timezone": "UTC",
                },
            )
            matches = data.get("response", []) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("查询%s赛程密度失败 team=%s: %s", side, team_id, exc)
            continue

        # 排除尚未开始的当前场比赛本身会重复计数，但近7天已踢场次影响疲劳度
        played_count = 0
        for m in matches:
            f = m.get("fixture", {}) or {}
            status = (f.get("status", {}) or {}).get("short", "")
            if status in {"FT", "AET", "PEN"}:
                played_count += 1

        if played_count >= 3:
            impact = "负面（疲劳度高）"
            weight = "高"
        elif played_count == 2:
            impact = "轻微负面"
            weight = "中"
        else:
            impact = "中性（体能充沛）"
            weight = "低"

        factors.append(
            {
                "factor": f"赛程密度·{label}（近7天已踢{played_count}场）",
                "impact": impact,
                "weight": weight,
            }
        )

    return factors


def _injury_factors(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    home_id: int | None,
    away_id: int | None,
) -> list[dict[str, str]]:
    """
    通过 /injuries?fixture=ID 查询双方伤停情况。
    """
    fixture_info = fixture.get("fixture", {}) or {}
    fixture_id = fixture_info.get("id")
    if not fixture_id:
        return []

    try:
        data = api.get("/injuries", {"fixture": fixture_id})
        injuries = data.get("response", []) or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("查询伤病失败 fixture=%s: %s", fixture_id, exc)
        return []

    home_injuries = 0
    away_injuries = 0
    for item in injuries:
        team = item.get("team", {}) or {}
        tid = team.get("id")
        if tid == home_id:
            home_injuries += 1
        elif tid == away_id:
            away_injuries += 1

    factors: list[dict[str, str]] = []
    if home_id:
        factors.append(_build_injury_factor("主队", home_injuries))
    if away_id:
        factors.append(_build_injury_factor("客队", away_injuries))
    return factors


def _build_injury_factor(side_label: str, count: int) -> dict[str, str]:
    if count >= 4:
        impact, weight = "负面（主力大面积伤缺）", "高"
    elif count >= 2:
        impact, weight = "轻微负面", "中"
    elif count == 1:
        impact, weight = "轻微影响", "低"
    else:
        impact, weight = "中性（无伤病）", "低"
    return {
        "factor": f"伤病·{side_label}（{count}人伤缺）",
        "impact": impact,
        "weight": weight,
    }


def _suspension_factors(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    home_id: int | None,
    away_id: int | None,
) -> list[dict[str, str]]:
    """
    通过 /fixtures/players?fixture=ID 间接查红黄牌，估算停赛风险。
    API-Football 的 /suspensions 端点有限，这里用上一场黄牌数近似。
    无数据时返回中性。
    """
    fixture_info = fixture.get("fixture", {}) or {}
    fixture_id = fixture_info.get("id")
    if not fixture_id:
        return []

    try:
        data = api.get("/fixtures/players", {"fixture": fixture_id, "team": home_id or away_id})
        players_resp = data.get("response", []) or []
    except Exception as exc:  # noqa: BLE001
        logger.warning("查询球员数据失败 fixture=%s: %s", fixture_id, exc)
        return []

    # 通常 fixture 未开始时无 players 数据，返回中性
    if not players_resp:
        return [
            {
                "factor": "停赛·双方",
                "impact": "中性（赛前无可查停赛数据）",
                "weight": "低",
            }
        ]

    home_yellows = away_yellows = 0
    home_reds = away_reds = 0
    for entry in players_resp:
        team = entry.get("team", {}) or {}
        tid = team.get("id")
        for player in entry.get("players", []) or []:
            stats = player.get("statistics", []) or []
            for s in stats:
                cards = s.get("cards", {}) or {}
                yellow = cards.get("yellow", 0) or 0
                red = cards.get("red", 0) or 0
                if tid == home_id:
                    home_yellows += yellow
                    home_reds += red
                elif tid == away_id:
                    away_yellows += yellow
                    away_reds += red

    factors: list[dict[str, str]] = []
    if home_id:
        factors.append(_build_suspension_factor("主队", home_yellows, home_reds))
    if away_id:
        factors.append(_build_suspension_factor("客队", away_yellows, away_reds))
    return factors


def _build_suspension_factor(side_label: str, yellows: int, reds: int) -> dict[str, str]:
    if reds > 0:
        impact, weight = f"负面（{reds}张红牌停赛风险）", "高"
    elif yellows >= 4:
        impact, weight = "负面（累计黄牌停赛风险）", "中"
    elif yellows >= 2:
        impact, weight = "轻微影响", "低"
    else:
        impact, weight = "中性（无停赛风险）", "低"
    return {
        "factor": f"停赛·{side_label}（近场{yellows}黄{reds}红）",
        "impact": impact,
        "weight": weight,
    }


def _travel_factor(fixture: dict[str, Any], away_team: dict[str, Any]) -> dict[str, str]:
    """
    客场旅程因子。API-Football fixture 不直接给双方城市距离，
    这里用 venue 与 away team 是否同国作为近似。
    """
    fixture_info = fixture.get("fixture", {}) or {}
    venue = fixture_info.get("venue", {}) or {}
    venue_city = (venue.get("city") or "").strip()
    away_country = (away_team.get("country") or "").strip()

    # 简化规则：若 venue 信息缺失，按中性处理
    if not venue_city:
        return {
            "factor": "客场旅程·客队",
            "impact": "中性（场地信息不足）",
            "weight": "低",
        }

    # 客队国别与场地城市无直接对照，默认按"国内客场"处理
    # 若是国际比赛日或欧战，可由 league 字段进一步判断，此处保持保守
    league = fixture.get("league", {}) or {}
    league_name = (league.get("name") or "").lower()
    if any(k in league_name for k in ("champions", "europa", "conference", "uefa")):
        return {
            "factor": f"客场旅程·客队（欧战远征 {venue_city}）",
            "impact": "负面（跨国远征疲劳）",
            "weight": "中",
        }

    return {
        "factor": f"客场旅程·客队（赴 {venue_city}）",
        "impact": "轻微负面（国内客场）",
        "weight": "低",
    }


# ----------------------------------------------------------------------------
# 剧本推断
# ----------------------------------------------------------------------------

def _build_scenarios(
    home_std: dict[str, Any],
    away_std: dict[str, Any],
    home_motivation: dict[str, str],
    away_motivation: dict[str, str],
    fundamental_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    基于基本面+战意推断 3 种可能剧本，概率之和 = 1.0。
    """
    home_level = home_motivation.get("level", _MOTIVATION_MEDIUM)
    away_level = away_motivation.get("level", _MOTIVATION_MEDIUM)

    home_rank = home_std.get("rank") or 0
    away_rank = away_std.get("rank") or 0
    home_points = home_std.get("points") or 0
    away_points = away_std.get("points") or 0
    home_gd = home_std.get("goal_diff") or 0
    away_gd = away_std.get("goal_diff") or 0

    # 近况（form_score 0~1）
    form = fundamental_data.get("form", {}) if fundamental_data else {}
    home_form = (form.get("home", {}) or {}).get("form_score", 0.5)
    away_form = (form.get("away", {}) or {}).get("form_score", 0.5)

    # 主客场优势：默认主队略占优
    home_bias = 0.10

    # 战意权重映射为数值
    level_weight = {
        _MOTIVATION_EXTREME: 0.30,
        _MOTIVATION_STRONG: 0.20,
        _MOTIVATION_MEDIUM: 0.10,
        _MOTIVATION_LOW: -0.05,
    }
    home_power = (
        home_points * 0.5
        + home_gd * 0.3
        + home_form * 30
        + level_weight.get(home_level, 0.10) * 20
        + home_bias * 20
    )
    away_power = (
        away_points * 0.5
        + away_gd * 0.3
        + away_form * 30
        + level_weight.get(away_level, 0.10) * 20
    )

    # 转为胜/平/负概率（softmax 近似）
    total = home_power + away_power + 5.0  # 平局基底
    p_home_raw = home_power / total
    p_away_raw = away_power / total
    p_draw_raw = 5.0 / total

    # 调整平局，避免过低
    p_draw = max(p_draw_raw, 0.20)
    remaining = 1.0 - p_draw
    scale = remaining / (p_home_raw + p_away_raw)
    p_home = p_home_raw * scale
    p_away = p_away_raw * scale

    # 兜底保证和为 1
    p_home, p_draw, p_away = _normalize(p_home, p_draw, p_away)

    # 剧本1：主队称雄
    scenario_home = {
        "name": "主队称雄",
        "probability": round(p_home, 2),
        "description": _describe_home_win_scenario(
            home_rank, away_rank, home_level, away_level, home_form, away_form
        ),
    }

    # 剧本2：势均力敌
    scenario_draw = {
        "name": "势均力敌",
        "probability": round(p_draw, 2),
        "description": _describe_draw_scenario(
            home_level, away_level, home_form, away_form
        ),
    }

    # 剧本3：客队逆袭
    scenario_away = {
        "name": "客队逆袭",
        "probability": round(p_away, 2),
        "description": _describe_away_win_scenario(
            home_rank, away_rank, home_level, away_level, home_form, away_form
        ),
    }

    # 最终再校验一次概率和
    s = scenario_home["probability"] + scenario_draw["probability"] + scenario_away["probability"]
    if s != 1.0:
        diff = 1.0 - s
        scenario_home["probability"] = round(scenario_home["probability"] + diff, 2)

    return [scenario_home, scenario_draw, scenario_away]


def _normalize(p1: float, p2: float, p3: float) -> tuple[float, float, float]:
    total = p1 + p2 + p3
    if total <= 0:
        return 0.4, 0.3, 0.3
    return p1 / total, p2 / total, p3 / total


def _describe_home_win_scenario(
    home_rank: int,
    away_rank: int,
    home_level: str,
    away_level: str,
    home_form: float,
    away_form: float,
) -> str:
    parts = ["主队凭借主场之利"]
    if home_rank and away_rank and home_rank < away_rank:
        parts.append(f"排名({home_rank})高于客队({away_rank})的综合优势")
    if home_level in (_MOTIVATION_EXTREME, _MOTIVATION_STRONG):
        parts.append("与争冠/欧战/保级战意的加持")
    if away_level == _MOTIVATION_LOW:
        parts.append("以及客队战意低落的契机")
    if home_form > 0.6:
        parts.append("近期状态火热")
    parts.append("掌控节奏并全取三分")
    return "，".join(parts) + "。"


def _describe_draw_scenario(
    home_level: str,
    away_level: str,
    home_form: float,
    away_form: float,
) -> str:
    parts = ["双方实力接近"]
    if home_level == away_level:
        parts.append(f"战意旗鼓相当（均{home_level}）")
    if abs(home_form - away_form) < 0.15:
        parts.append("近期状态相近")
    parts.append("比赛陷入拉锯，最终握手言和")
    return "，".join(parts) + "。"


def _describe_away_win_scenario(
    home_rank: int,
    away_rank: int,
    home_level: str,
    away_level: str,
    home_form: float,
    away_form: float,
) -> str:
    parts = ["客队反客为主"]
    if home_rank and away_rank and away_rank < home_rank:
        parts.append(f"排名({away_rank})优于主队({home_rank})的硬实力压制")
    if away_level in (_MOTIVATION_EXTREME, _MOTIVATION_STRONG):
        parts.append("凭借强烈的抢分战意")
    if home_level == _MOTIVATION_LOW:
        parts.append("利用主队无欲无求的心态")
    if away_form > 0.6:
        parts.append("以及近期出色状态")
    parts.append("客场带走胜利")
    return "，".join(parts) + "。"
