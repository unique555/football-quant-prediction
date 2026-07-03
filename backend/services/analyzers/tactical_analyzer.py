"""
战术分析器 — 球队战术风格 / 攻防特征 / 对位匹配

数据来源：API-Football /teams/statistics（含 shots / passes / possession / cards）
依赖 fundamental_analyzer 提供的主客战绩与近况数据。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)


def analyze(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    fundamental_data: dict[str, Any],
) -> dict[str, Any]:
    """
    战术分析主入口。

    Args:
        api: API-Football 客户端，提供 .get(path, params) 方法
        fixture: API-Football fixture 原始数据
        fundamental_data: fundamental_analyzer.analyze 的返回值，
            预期含 home_record / away_record 等字段

    Returns:
        {
            "tactical_style": {
                "home": {possession, shots_avg, shots_on_target_avg,
                         pass_accuracy, pressing_success, defense_actions,
                         style_label},
                "away": {...},
            },
            "strengths_weaknesses": {
                "home": {"attack": str, "defense": str},
                "away": {"attack": str, "defense": str},
            },
            "matchup": {
                "midfield": str, "wing": str, "set_piece": str,
                "tempo": str, "prediction": str,
            },
        }
        数据不足时返回同结构的空字典（字符串字段为 ""）。
    """
    league = fixture.get("league", {}) or {}
    teams = fixture.get("teams", {}) or {}
    season = league.get("season") or datetime.now(timezone.utc).year
    league_id = league.get("id")
    home_id = (teams.get("home", {}) or {}).get("id")
    away_id = (teams.get("away", {}) or {}).get("id")

    # 从 fundamental_data 获取已计算的主客战绩
    home_record = fundamental_data.get("home_record", {}) or {}
    away_record = fundamental_data.get("away_record", {}) or {}

    # 拉取完整统计（含 shots / passes / cards）
    home_stats = _fetch_full_stats(api, league_id, home_id, season)
    away_stats = _fetch_full_stats(api, league_id, away_id, season)

    # 数据不足时返回空结构，不抛错
    if not home_stats or not away_stats:
        logger.info(
            "tactical_analyzer: 数据不足 home=%s away=%s，返回空结构",
            bool(home_stats), bool(away_stats),
        )
        return _empty_result()

    home_style = _infer_tactical_style(home_stats)
    away_style = _infer_tactical_style(away_stats)

    home_sw = _infer_strengths_weaknesses(home_stats, home_record)
    away_sw = _infer_strengths_weaknesses(away_stats, away_record)

    matchup = _infer_matchup(
        home_style, away_style, home_sw, away_sw, home_record, away_record
    )

    return {
        "tactical_style": {"home": home_style, "away": away_style},
        "strengths_weaknesses": {"home": home_sw, "away": away_sw},
        "matchup": matchup,
    }


# ---------------------------------------------------------------------------
# 数据获取与解析
# ---------------------------------------------------------------------------

def _fetch_full_stats(
    api: ApiFootballClient,
    league_id: int | None,
    team_id: int | None,
    season: int,
) -> dict[str, Any]:
    """拉取 /teams/statistics 并解析为战术指标。"""
    if not league_id or not team_id:
        return {}
    try:
        data = api.get(
            "/teams/statistics",
            {"league": league_id, "team": team_id, "season": season},
        )
    except Exception as exc:  # noqa: BLE001 — 容错，不向上抛
        logger.warning("tactical_analyzer: 拉取统计失败 team=%s err=%s", team_id, exc)
        return {}
    resp = data.get("response", {}) or {}
    if not resp:
        return {}
    return _parse_full_stats(resp)


def _parse_full_stats(resp: dict[str, Any]) -> dict[str, Any]:
    """从 /teams/statistics 响应中提取战术相关字段。"""
    fixtures = resp.get("fixtures", {}) or {}
    played = fixtures.get("played", {}).get("total", 0) or 0
    if played == 0:
        return {}

    goals = resp.get("goals", {}) or {}
    goals_for_total = (
        goals.get("for", {}).get("total", {}).get("total", 0) or 0
    )
    goals_against_total = (
        goals.get("against", {}).get("total", {}).get("total", 0) or 0
    )

    shots = resp.get("shots", {}) or {}
    shots_total = shots.get("total", 0) or 0
    shots_on_target = shots.get("on_target", 0) or 0

    passes = resp.get("passes", {}) or {}
    passes_total = passes.get("total", 0) or 0
    passes_accuracy = _parse_pct(passes.get("accuracy", "0%"))

    possession = resp.get("possession", {}) or {}
    avg_possession = _parse_pct(possession.get("average", "0%"))

    cards = resp.get("cards", {}) or {}
    yellow = (cards.get("yellow", {}) or {}).get("total", 0) or 0
    red = (cards.get("red", {}) or {}).get("total", 0) or 0

    clean_sheets = (resp.get("clean_sheet", {}) or {}).get("total", 0) or 0
    failed_to_score = (
        (resp.get("failed_to_score", {}) or {}).get("total", 0) or 0
    )

    penalty = resp.get("penalty", {}) or {}
    penalty_scored = (penalty.get("scored", {}) or {}).get("total", 0) or 0
    penalty_missed = (penalty.get("missed", {}) or {}).get("total", 0) or 0

    return {
        "team_name": (resp.get("team", {}) or {}).get("name", ""),
        "matches_played": played,
        "goals_for_avg": round(goals_for_total / played, 2),
        "goals_against_avg": round(goals_against_total / played, 2),
        "shots_avg": round(shots_total / played, 2),
        "shots_on_target_avg": round(shots_on_target / played, 2),
        "shots_accuracy": (
            round(shots_on_target / shots_total, 2) if shots_total else 0.0
        ),
        "pass_accuracy": round(passes_accuracy, 2),
        "passes_avg": round(passes_total / played, 2),
        "avg_possession": round(avg_possession, 2),
        "yellow_cards_avg": round(yellow / played, 2),
        "red_cards_avg": round(red / played, 2),
        "clean_sheet_rate": round(clean_sheets / played, 2),
        "failed_to_score_rate": round(failed_to_score / played, 2),
        "penalty_scored": penalty_scored,
        "penalty_missed": penalty_missed,
    }


def _parse_pct(s: Any) -> float:
    """解析 '55%' / '0.55' / None 等形式为 0~1 浮点数。"""
    if s is None:
        return 0.0
    try:
        return float(str(s).rstrip("%")) / 100
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# 战术风格推断
# ---------------------------------------------------------------------------

def _infer_tactical_style(stats: dict[str, Any]) -> dict[str, Any]:
    """从统计数据推断战术风格指标。"""
    possession = stats.get("avg_possession", 0.0)
    shots_avg = stats.get("shots_avg", 0.0)
    shots_on_target_avg = stats.get("shots_on_target_avg", 0.0)
    pass_accuracy = stats.get("pass_accuracy", 0.0)
    yellow_avg = stats.get("yellow_cards_avg", 0.0)
    red_avg = stats.get("red_cards_avg", 0.0)
    clean_sheet_rate = stats.get("clean_sheet_rate", 0.0)
    goals_against_avg = stats.get("goals_against_avg", 0.0)

    # pressing_success：用防守强度（牌数）+ 零封率 + 失球少 综合近似
    # API-Football 无直接逼抢数据，此处用代理指标
    pressing_success = round(
        min(
            1.0,
            0.3 * clean_sheet_rate
            + 0.4 * max(0.0, 1.0 - goals_against_avg / 2.0)
            + 0.3 * min(1.0, yellow_avg / 2.5),
        ),
        2,
    )

    # defense_actions：失球越少 + 牌数越多 ≈ 防守动作越积极
    defense_actions = round(
        max(0.0, 1.5 - goals_against_avg) * 10.0
        + yellow_avg
        + red_avg * 2.0,
        2,
    )

    return {
        "possession": round(possession, 2),
        "shots_avg": round(shots_avg, 2),
        "shots_on_target_avg": round(shots_on_target_avg, 2),
        "pass_accuracy": round(pass_accuracy, 2),
        "pressing_success": pressing_success,
        "defense_actions": defense_actions,
        "style_label": _style_label(stats),
    }


def _style_label(stats: dict[str, Any]) -> str:
    """根据关键指标生成战术风格标签。"""
    possession = stats.get("avg_possession", 0.0)
    shots_avg = stats.get("shots_avg", 0.0)
    pass_accuracy = stats.get("pass_accuracy", 0.0)
    goals_against_avg = stats.get("goals_against_avg", 0.0)
    clean_sheet_rate = stats.get("clean_sheet_rate", 0.0)

    labels: list[str] = []

    if possession > 0.55:
        labels.append("控球型")
    elif possession < 0.45:
        labels.append("防守反击型")

    if shots_avg >= 14:
        labels.append("进攻型")

    if pass_accuracy > 0.82:
        labels.append("传控型")

    if goals_against_avg < 1.0 and clean_sheet_rate > 0.35:
        labels.append("防守稳固型")

    if not labels:
        labels.append("均衡型")

    return "/".join(labels)


# ---------------------------------------------------------------------------
# 攻防特征推断
# ---------------------------------------------------------------------------

def _infer_strengths_weaknesses(
    stats: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, str]:
    """根据进球/失球/射门等推断攻防特征描述。"""
    # 优先用 fundamental 的 record（主客场拆分更准确），fallback 到 statistics
    gf_avg = (
        record.get("goals_for_avg")
        or stats.get("goals_for_avg", 0.0)
        or 0.0
    )
    ga_avg = (
        record.get("goals_against_avg")
        or stats.get("goals_against_avg", 0.0)
        or 0.0
    )
    shots_avg = stats.get("shots_avg", 0.0)
    shots_acc = stats.get("shots_accuracy", 0.0)
    cs_rate = stats.get("clean_sheet_rate", 0.0)
    fts_rate = stats.get("failed_to_score_rate", 0.0)

    # 进攻特征
    if gf_avg >= 2.0:
        attack = (
            "进攻强势（场均进球 %.2f，场均射门 %.1f 次，命中率 %.0f%%）"
            % (gf_avg, shots_avg, shots_acc * 100)
        )
    elif gf_avg >= 1.3:
        attack = (
            "进攻稳定（场均进球 %.2f，射门命中率 %.0f%%）"
            % (gf_avg, shots_acc * 100)
        )
    elif gf_avg >= 0.8:
        attack = (
            "进攻偏弱（场均进球 %.2f，未能进球率 %.0f%%）"
            % (gf_avg, fts_rate * 100)
        )
    else:
        attack = "进攻乏力（场均进球 %.2f，难以制造威胁）" % gf_avg

    # 防守特征
    if ga_avg < 0.8 and cs_rate > 0.4:
        defense = (
            "防守坚固（场均失球 %.2f，零封率 %.0f%%）"
            % (ga_avg, cs_rate * 100)
        )
    elif ga_avg < 1.2:
        defense = "防守稳健（场均失球 %.2f）" % ga_avg
    elif ga_avg < 1.8:
        defense = "防守一般（场均失球 %.2f）" % ga_avg
    else:
        defense = "防守薄弱（场均失球 %.2f，需警惕）" % ga_avg

    return {"attack": attack, "defense": defense}


# ---------------------------------------------------------------------------
# 对位分析
# ---------------------------------------------------------------------------

def _infer_matchup(
    home_style: dict[str, Any],
    away_style: dict[str, Any],
    home_sw: dict[str, str],
    away_sw: dict[str, str],
    home_record: dict[str, Any],
    away_record: dict[str, Any],
) -> dict[str, str]:
    """根据双方战术风格与攻防特征进行对位分析。"""
    home_poss = home_style.get("possession", 0.0)
    away_poss = away_style.get("possession", 0.0)
    home_pass = home_style.get("pass_accuracy", 0.0)
    away_pass = away_style.get("pass_accuracy", 0.0)

    # 中场：控球率 + 传球精度综合
    home_mid = home_poss + home_pass * 0.5
    away_mid = away_poss + away_pass * 0.5
    if abs(home_mid - away_mid) < 0.1:
        midfield = "中场实力接近，控球权争夺激烈"
    elif home_mid > away_mid:
        midfield = (
            "主队中场占优（控球率 %.0f%% vs %.0f%%，传球精度 %.0f%% vs %.0f%%）"
            % (
                home_poss * 100, away_poss * 100,
                home_pass * 100, away_pass * 100,
            )
        )
    else:
        midfield = (
            "客队中场占优（控球率 %.0f%% vs %.0f%%，传球精度 %.0f%% vs %.0f%%）"
            % (
                away_poss * 100, home_poss * 100,
                away_pass * 100, home_pass * 100,
            )
        )

    # 边路 / 进攻威胁：射门数 + 进球数
    home_shots = home_style.get("shots_avg", 0.0)
    away_shots = away_style.get("shots_avg", 0.0)
    home_gf = home_record.get("goals_for_avg", 0.0) or 0.0
    away_gf = away_record.get("goals_for_avg", 0.0) or 0.0
    if home_shots > away_shots * 1.2 and home_gf > away_gf:
        wing = (
            "主队进攻端更具威胁（场均射门 %.1f vs %.1f，进球 %.2f vs %.2f）"
            % (home_shots, away_shots, home_gf, away_gf)
        )
    elif away_shots > home_shots * 1.2 and away_gf > home_gf:
        wing = (
            "客队进攻端更具威胁（场均射门 %.1f vs %.1f，进球 %.2f vs %.2f）"
            % (away_shots, home_shots, away_gf, home_gf)
        )
    else:
        wing = "双方进攻端旗鼓相当（射门 %.1f vs %.1f）" % (home_shots, away_shots)

    # 定位球：防守动作激烈程度 + 点球
    home_da = home_style.get("defense_actions", 0.0)
    away_da = away_style.get("defense_actions", 0.0)
    if home_da + away_da > 25:
        set_piece = (
            "双方防守动作激烈（主队 %.1f / 客队 %.1f），定位球机会较多"
            % (home_da, away_da)
        )
    else:
        set_piece = (
            "双方防守相对克制（主队 %.1f / 客队 %.1f），定位球影响有限"
            % (home_da, away_da)
        )

    # 节奏
    poss_diff = abs(home_poss - away_poss)
    if poss_diff > 0.15 and max(home_poss, away_poss) > 0.55:
        tempo = "节奏受控于控球方，比赛可能偏慢"
    else:
        tempo = "比赛节奏较快，攻防转换频繁"

    prediction = _build_prediction(
        home_style, away_style, home_record, away_record
    )

    return {
        "midfield": midfield,
        "wing": wing,
        "set_piece": set_piece,
        "tempo": tempo,
        "prediction": prediction,
    }


def _build_prediction(
    home_style: dict[str, Any],
    away_style: dict[str, Any],
    home_record: dict[str, Any],
    away_record: dict[str, Any],
) -> str:
    """基于战术与基本面指标给出综合预测描述。"""
    home_score = 0
    away_score = 0

    home_gf = home_record.get("goals_for_avg", 0.0) or 0.0
    away_gf = away_record.get("goals_for_avg", 0.0) or 0.0
    home_ga = home_record.get("goals_against_avg", 0.0) or 0.0
    away_ga = away_record.get("goals_against_avg", 0.0) or 0.0

    # 进攻能力
    if home_gf > away_gf + 0.3:
        home_score += 2
    elif away_gf > home_gf + 0.3:
        away_score += 2
    elif home_gf > away_gf:
        home_score += 1
    elif away_gf > home_gf:
        away_score += 1

    # 防守能力
    if home_ga < away_ga - 0.3:
        home_score += 1
    elif away_ga < home_ga - 0.3:
        away_score += 1

    # 控球优势
    home_poss = home_style.get("possession", 0.0)
    away_poss = away_style.get("possession", 0.0)
    if home_poss > away_poss + 0.05:
        home_score += 1
    elif away_poss > home_poss + 0.05:
        away_score += 1

    # 主场加成
    home_score += 1

    if home_score > away_score + 2:
        return "综合战术与基本面，主队更占优势，倾向于主胜"
    if away_score > home_score + 1:
        return "综合战术与基本面，客队略占优势，倾向于客胜或平局"
    return "双方实力接近，比赛结果存在不确定性，建议关注进球数盘口"


# ---------------------------------------------------------------------------
# 空结构
# ---------------------------------------------------------------------------

def _empty_team_style() -> dict[str, Any]:
    return {
        "possession": 0.0,
        "shots_avg": 0.0,
        "shots_on_target_avg": 0.0,
        "pass_accuracy": 0.0,
        "pressing_success": 0.0,
        "defense_actions": 0.0,
        "style_label": "",
    }


def _empty_result() -> dict[str, Any]:
    return {
        "tactical_style": {
            "home": _empty_team_style(),
            "away": _empty_team_style(),
        },
        "strengths_weaknesses": {
            "home": {"attack": "", "defense": ""},
            "away": {"attack": "", "defense": ""},
        },
        "matchup": {
            "midfield": "",
            "wing": "",
            "set_piece": "",
            "tempo": "",
            "prediction": "",
        },
    }
