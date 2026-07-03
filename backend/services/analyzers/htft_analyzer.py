"""
半全场分析器 — HT/FT 概率 / 半场大小球 / edge

数据来源：fundamental_analyzer 提供的主客进球均值 + odds_aggregates 中的 HT/FT 赔率
用泊松分布建模半场与全场比分。
简化假设：半场结果与全场结果独立，P(HT=X, FT=Y) = P(HT=X) × P(FT=Y)。
半场 lambda 取全场 lambda 的 45%。
"""

from __future__ import annotations

import logging
import math
from typing import Any

from services.telegram_mvp.api_football import ApiFootballClient

logger = logging.getLogger(__name__)

# 半场 lambda 占全场 lambda 的比例
_HT_LAMBDA_RATIO = 0.45
# 泊松计算的最大单队进球数
_MAX_GOALS = 6

# HT/FT 九种组合键：第一位为半场结果，第二位为全场结果
# H=主胜 D=平 A=客胜
_HTFT_KEYS = ["HH", "HD", "HA", "DH", "DD", "DA", "AH", "AD", "AA"]


def analyze(
    api: ApiFootballClient,
    fixture: dict[str, Any],
    fundamental_data: dict[str, Any],
    odds_aggregates: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    半全场分析主入口。

    Args:
        api: API-Football 客户端（本分析器不直接调用，保留接口一致性）
        fixture: API-Football fixture 原始数据
        fundamental_data: fundamental_analyzer.analyze 的返回值
        odds_aggregates: dict，键为市场名（含可能的 "ht_ft"），值为 MarketAggregate 或 None

    Returns:
        {
            "htft_probs": {"HH": p, "HD": p, ...9 种},
            "market_implied": {同上，从赔率计算，无则空 dict},
            "ht_over_under": {"line": 0.5, "over_prob": p, "under_prob": p},
            "best_combo": str,  # 如 "HH"
            "edge": float|None,
        }
        数据不足时返回空结构。
    """
    odds_aggregates = odds_aggregates or {}
    fundamental_data = fundamental_data or {}

    home_record = fundamental_data.get("home_record", {}) or {}
    away_record = fundamental_data.get("away_record", {}) or {}

    home_xg = _estimate_xg(home_record, away_record, "home")
    away_xg = _estimate_xg(home_record, away_record, "away")

    if home_xg <= 0 or away_xg <= 0:
        logger.info(
            "htft_analyzer: xG 数据不足 home_xg=%s away_xg=%s，返回空结构",
            home_xg, away_xg,
        )
        return _empty_result()

    # 半场 lambda
    ht_home_xg = home_xg * _HT_LAMBDA_RATIO
    ht_away_xg = away_xg * _HT_LAMBDA_RATIO

    # HT/FT 概率（假设半场与全场独立）
    htft_probs = _compute_htft_probs(ht_home_xg, ht_away_xg, home_xg, away_xg)

    # 市场隐含概率（若有 ht_ft 赔率）
    market_implied = _extract_market_implied(odds_aggregates)

    # 半场大小球 0.5：P(HT 有进球) = 1 - P(0 球) = 1 - e^(-λ_total_ht)
    ht_total_lambda = ht_home_xg + ht_away_xg
    ht_over_prob = 1.0 - math.exp(-ht_total_lambda) if ht_total_lambda > 0 else 0.0
    ht_over_under = {
        "line": 0.5,
        "over_prob": round(ht_over_prob, 4),
        "under_prob": round(1.0 - ht_over_prob, 4),
    }

    # 最佳组合（模型概率最高的 HT/FT）
    best_combo = max(htft_probs, key=lambda k: htft_probs[k])

    # edge：最佳组合的模型概率 vs 市场隐含概率
    edge = None
    if market_implied and best_combo in market_implied:
        model_prob = htft_probs[best_combo]
        market_prob = market_implied[best_combo]
        edge = round(model_prob - market_prob, 4)

    return {
        "htft_probs": htft_probs,
        "market_implied": market_implied,
        "ht_over_under": ht_over_under,
        "best_combo": best_combo,
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
    用本队进攻能力（goals_for_avg）与对手防守漏洞（goals_against_avg）的均值。
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


def _match_result_probs(home_xg: float, away_xg: float) -> tuple[float, float, float]:
    """
    计算主胜 / 平 / 客胜概率（泊松模型，假设主客进球独立）。
    返回 (p_home_win, p_draw, p_away_win)。
    """
    p_home = p_draw = p_away = 0.0
    for i in range(_MAX_GOALS + 1):
        p_i = _poisson_pmf(i, home_xg)
        for j in range(_MAX_GOALS + 1):
            p_ij = p_i * _poisson_pmf(j, away_xg)
            if i > j:
                p_home += p_ij
            elif i == j:
                p_draw += p_ij
            else:
                p_away += p_ij
    return p_home, p_draw, p_away


# ---------------------------------------------------------------------------
# HT/FT 概率计算
# ---------------------------------------------------------------------------

def _compute_htft_probs(
    ht_home_xg: float,
    ht_away_xg: float,
    ft_home_xg: float,
    ft_away_xg: float,
) -> dict[str, float]:
    """
    计算 9 种 HT/FT 组合概率。

    简化假设：半场结果与全场结果独立。
    P(HT=X, FT=Y) = P(HT=X) × P(FT=Y)
    """
    ht_h, ht_d, ht_a = _match_result_probs(ht_home_xg, ht_away_xg)
    ft_h, ft_d, ft_a = _match_result_probs(ft_home_xg, ft_away_xg)

    ht_results = {"H": ht_h, "D": ht_d, "A": ht_a}
    ft_results = {"H": ft_h, "D": ft_d, "A": ft_a}

    probs: dict[str, float] = {}
    for ht in ("H", "D", "A"):
        for ft in ("H", "D", "A"):
            key = ht + ft
            probs[key] = round(ht_results[ht] * ft_results[ft], 4)
    return probs


# ---------------------------------------------------------------------------
# 市场隐含概率
# ---------------------------------------------------------------------------

def _extract_market_implied(
    odds_aggregates: dict[str, Any]
) -> dict[str, float]:
    """
    从 odds_aggregates["ht_ft"] 提取市场隐含概率（no_vig_probs）。
    无 ht_ft 市场时返回空 dict。
    """
    htft_agg = odds_aggregates.get("ht_ft")
    if not htft_agg:
        return {}
    no_vig = htft_agg.no_vig_probs or {}
    result: dict[str, float] = {}
    for key in _HTFT_KEYS:
        if key in no_vig:
            result[key] = round(no_vig[key], 4)
    return result


# ---------------------------------------------------------------------------
# 空结构
# ---------------------------------------------------------------------------

def _empty_result() -> dict[str, Any]:
    return {
        "htft_probs": {k: 0.0 for k in _HTFT_KEYS},
        "market_implied": {},
        "ht_over_under": {"line": 0.5, "over_prob": 0.0, "under_prob": 0.0},
        "best_combo": "",
        "edge": None,
    }
