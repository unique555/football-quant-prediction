"""
进球市场分析器 — 大小球 / BTTS / 进球分布 / 比分预测

数据来源：fundamental_analyzer 提供的主客进球均值（goals_for_avg / goals_against_avg）
        + odds_aggregates 中的大小球与 BTTS 赔率聚合
用泊松分布建模进球概率，假设主客进球相互独立。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)

# 泊松分布计算的最大进球数（进球分布返回 0~5）
_DIST_MAX_GOALS = 5
# 比分预测的单队最大进球数
_SCORE_MAX_GOALS = 6


def analyze(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    fundamental_data: dict[str, Any],
    odds_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    进球市场分析主入口。

    Args:
        api: API-Football 客户端（本分析器不直接调用，保留接口一致性）
        fixture: API-Football fixture 原始数据
        fundamental_data: fundamental_analyzer.analyze 的返回值，
            预期含 home_record / away_record 的 goals_for_avg / goals_against_avg
        odds_aggregates: dict，键为市场名（"1x2" / "over_under" / "btts" ...），
            值为 MarketAggregate 或 None

    Returns:
        {
            "over_under": {line, over_odds, under_odds, over_prob, under_prob},
            "expected_total_goals": float,
            "btts": {yes_odds, no_odds, yes_prob, no_prob},
            "goal_distribution": {0: p, 1: p, ...5: p},
            "top_scores": [("2-1", 0.12), ...],
            "edge": {"over": float|None, "btts_yes": float|None},
        }
        数据不足时返回同结构的空字典。
    """
    odds_aggregates = odds_aggregates or {}
    fundamental_data = fundamental_data or {}

    home_record = fundamental_data.get("home_record", {}) or {}
    away_record = fundamental_data.get("away_record", {}) or {}

    home_xg = _estimate_xg(home_record, away_record, "home")
    away_xg = _estimate_xg(home_record, away_record, "away")

    if home_xg <= 0 or away_xg <= 0:
        logger.info(
            "goals_analyzer: xG 数据不足 home_xg=%s away_xg=%s，返回空结构",
            home_xg, away_xg,
        )
        return _empty_result()

    lambda_total = home_xg + away_xg

    over_under = _build_over_under(odds_aggregates, lambda_total)
    expected_total = round(lambda_total, 2)
    btts = _build_btts(home_xg, away_xg, odds_aggregates)
    goal_distribution = _poisson_distribution(lambda_total, _DIST_MAX_GOALS)
    top_scores = _top_scores(home_xg, away_xg, top_n=3)
    edge = _compute_edge(over_under, btts, lambda_total)

    return {
        "over_under": over_under,
        "expected_total_goals": expected_total,
        "btts": btts,
        "goal_distribution": goal_distribution,
        "top_scores": top_scores,
        "edge": edge,
    }


# ---------------------------------------------------------------------------
# xG 估算
# ---------------------------------------------------------------------------

def _estimate_xg(
    home_record: dict[str, Any],
    away_record: dict[str, Any],
    side: str,
) -> float:
    """
    估算预期进球数。

    用本队进攻能力（goals_for_avg）与对手防守漏洞（goals_against_avg）的均值，
    比单一指标更稳健。数据不全时回退到单一指标。
    """
    if side == "home":
        attack = _safe_float(home_record.get("goals_for_avg"))
        defense = _safe_float(away_record.get("goals_against_avg"))
    else:
        attack = _safe_float(away_record.get("goals_for_avg"))
        defense = _safe_float(home_record.get("goals_against_avg"))

    if attack and defense:
        return round((attack + defense) / 2, 3)
    return attack or defense or 0.0


def _safe_float(value: Any) -> float:
    try:
        f = float(value)
        return f if f > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# 泊松分布
# ---------------------------------------------------------------------------

def _poisson_pmf(k: int, lam: float) -> float:
    """泊松分布概率质量函数 P(X=k; λ)。"""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_distribution(lam: float, max_goals: int) -> dict[int, float]:
    """返回 {0: p, 1: p, ...max_goals: p} 的进球分布。"""
    return {k: round(_poisson_pmf(k, lam), 4) for k in range(max_goals + 1)}


def _poisson_over_prob(lam: float, line: float) -> float:
    """
    P(total > line)，用泊松累计分布计算。
    对 2.5 线：over = P(>=3) = 1 - P(0) - P(1) - P(2)。
    """
    threshold = math.floor(line)
    cum = sum(_poisson_pmf(k, lam) for k in range(threshold + 1))
    return 1.0 - cum


# ---------------------------------------------------------------------------
# 大小球
# ---------------------------------------------------------------------------

def _build_over_under(
    odds_aggregates: dict[str, Any], lambda_total: float
) -> dict[str, Any]:
    """构建大小球分析结果。无赔率时仍返回模型计算的概率。"""
    ou_agg = odds_aggregates.get("over_under")

    if not ou_agg:
        # 无赔率数据，用模型计算 2.5 线
        line = 2.5
        over_prob = _poisson_over_prob(lambda_total, line)
        return {
            "line": line,
            "over_odds": None,
            "under_odds": None,
            "over_prob": round(over_prob, 4),
            "under_prob": round(1.0 - over_prob, 4),
        }

    avg_odds = ou_agg.avg_odds or {}
    no_vig = ou_agg.no_vig_probs or {}
    line = avg_odds.get("line", 2.5)
    over_odds = avg_odds.get("over")
    under_odds = avg_odds.get("under")
    over_prob = no_vig.get("over", 0.0)
    under_prob = no_vig.get("under", 0.0)

    return {
        "line": line,
        "over_odds": over_odds,
        "under_odds": under_odds,
        "over_prob": round(over_prob, 4),
        "under_prob": round(under_prob, 4),
    }


# ---------------------------------------------------------------------------
# BTTS（双方都进球）
# ---------------------------------------------------------------------------

def _build_btts(
    home_xg: float,
    away_xg: float,
    odds_aggregates: dict[str, Any],
) -> dict[str, Any]:
    """
    P(both score) = P(home>0) * P(away>0)，假设独立。
    无 BTTS 赔率时仅返回模型概率。
    """
    p_home_scores = 1.0 - _poisson_pmf(0, home_xg)
    p_away_scores = 1.0 - _poisson_pmf(0, away_xg)
    yes_prob = p_home_scores * p_away_scores
    no_prob = 1.0 - yes_prob

    btts_agg = odds_aggregates.get("btts")
    yes_odds = None
    no_odds = None
    if btts_agg:
        avg_odds = btts_agg.avg_odds or {}
        yes_odds = avg_odds.get("yes")
        no_odds = avg_odds.get("no")

    return {
        "yes_odds": yes_odds,
        "no_odds": no_odds,
        "yes_prob": round(yes_prob, 4),
        "no_prob": round(no_prob, 4),
    }


# ---------------------------------------------------------------------------
# 比分预测
# ---------------------------------------------------------------------------

def _top_scores(home_xg: float, away_xg: float, top_n: int = 3) -> list[tuple[str, float]]:
    """
    用泊松联合分布计算最可能比分 top N。
    P(home=i, away=j) = P(i; λ_h) * P(j; λ_a)，假设独立。
    """
    scores: list[tuple[str, float]] = []
    for i in range(_SCORE_MAX_GOALS + 1):
        for j in range(_SCORE_MAX_GOALS + 1):
            prob = _poisson_pmf(i, home_xg) * _poisson_pmf(j, away_xg)
            scores.append((f"{i}-{j}", prob))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [(label, round(p, 4)) for label, p in scores[:top_n]]


# ---------------------------------------------------------------------------
# Edge 计算
# ---------------------------------------------------------------------------

def _compute_edge(
    over_under: dict[str, Any],
    btts: dict[str, Any],
    lambda_total: float,
) -> dict[str, Any]:
    """
    edge = 模型概率 - 市场隐含概率（1/赔率）。
    无赔率时为 None。
    """
    edge_over = None
    line = over_under.get("line")
    over_odds = over_under.get("over_odds")
    if line and over_odds:
        model_prob = _poisson_over_prob(lambda_total, line)
        market_prob = 1.0 / over_odds
        edge_over = round(model_prob - market_prob, 4)

    edge_btts_yes = None
    yes_odds = btts.get("yes_odds")
    if yes_odds:
        model_prob = btts["yes_prob"]
        market_prob = 1.0 / yes_odds
        edge_btts_yes = round(model_prob - market_prob, 4)

    return {"over": edge_over, "btts_yes": edge_btts_yes}


# ---------------------------------------------------------------------------
# 空结构
# ---------------------------------------------------------------------------

def _empty_result() -> dict[str, Any]:
    return {
        "over_under": {
            "line": 0.0,
            "over_odds": None,
            "under_odds": None,
            "over_prob": 0.0,
            "under_prob": 0.0,
        },
        "expected_total_goals": 0.0,
        "btts": {
            "yes_odds": None,
            "no_odds": None,
            "yes_prob": 0.0,
            "no_prob": 0.0,
        },
        "goal_distribution": {k: 0.0 for k in range(_DIST_MAX_GOALS + 1)},
        "top_scores": [],
        "edge": {"over": None, "btts_yes": None},
    }
