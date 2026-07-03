"""
第四步：市场定价检验 (优化版)

优化点:
  #14 高赔率场景 EV 折扣 — 赔率> ceiling 时打折扣
  #16 输出含置信度
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.config.settings import PricingConfig, engine_config


class PricingVerdict(Enum):
    FAIR = "fair"
    OVERPRICED = "overpriced"
    UNDERVALUED = "undervalued"


@dataclass
class PricingResult:
    verdict: PricingVerdict
    ev_home: float = 0.0
    ev_draw: float = 0.0
    ev_away: float = 0.0
    best_value_side: Optional[str] = None
    best_ev: float = 0.0
    home_odds_deviation: float = 0.0
    draw_odds_deviation: float = 0.0
    away_odds_deviation: float = 0.0
    payout_analysis: str = ""
    # 新增
    ev_confidence_penalty: float = 0.0  # 高赔率场景的置信度惩罚 (#14)
    notes: list[str] = field(default_factory=list)


def check_market_pricing(
    model_prob_home: float,
    model_prob_draw: float,
    model_prob_away: float,
    market_home_odds: float,
    market_draw_odds: float,
    market_away_odds: float,
    config: Optional[PricingConfig] = None,
) -> PricingResult:
    """
    市场定价检验 (高赔率感知版)
    """
    cfg = config or engine_config.pricing
    notes = []

    # ---- 1. EV (含 #14 高赔率折扣) ----
    ev_home = model_prob_home * market_home_odds - 1
    ev_draw = model_prob_draw * market_draw_odds - 1
    ev_away = model_prob_away * market_away_odds - 1

    # 高赔率折扣
    discount_home = _high_odds_discount(market_home_odds, cfg)
    discount_draw = _high_odds_discount(market_draw_odds, cfg)
    discount_away = _high_odds_discount(market_away_odds, cfg)

    ev_home_adj = ev_home * discount_home
    ev_draw_adj = ev_draw * discount_draw
    ev_away_adj = ev_away * discount_away

    penalty = max(1 - discount_home, 1 - discount_draw, 1 - discount_away)
    if penalty > 0:
        notes.append(f"高赔率EV折扣系数: {1 - penalty:.0%}")

    # ---- 2. 偏差 ----
    fair_home = 1 / model_prob_home if model_prob_home > 0 else 999
    fair_draw = 1 / model_prob_draw if model_prob_draw > 0 else 999
    fair_away = 1 / model_prob_away if model_prob_away > 0 else 999

    dev_home = market_home_odds / fair_home - 1
    dev_draw = market_draw_odds / fair_draw - 1
    dev_away = market_away_odds / fair_away - 1

    # ---- 3. 价值洼地 ----
    ev_map = {"home": ev_home_adj, "draw": ev_draw_adj, "away": ev_away_adj}
    best_side = max(ev_map, key=ev_map.get)
    best_ev = ev_map[best_side]

    if best_ev > cfg.ev_value_threshold:
        best_value_side = best_side
        notes.append(f"价值洼地: {best_side} EV={best_ev:.2%}")
    elif best_ev > 0:
        best_value_side = best_side
        notes.append(f"微弱价值: {best_side}")
    else:
        best_value_side = None
        notes.append("无正EV方向，市场定价充分")

    # ---- 4. 水位分析 ----
    payout_analysis = _analyze_payout(
        market_home_odds, market_draw_odds, market_away_odds, dev_home, dev_draw, dev_away
    )

    # ---- 5. 综合 ----
    if best_ev > 0.08:
        verdict = PricingVerdict.UNDERVALUED
    elif best_ev > cfg.ev_overpriced_threshold:
        verdict = PricingVerdict.FAIR
    else:
        verdict = PricingVerdict.OVERPRICED

    return PricingResult(
        verdict=verdict,
        ev_home=round(ev_home, 4),
        ev_draw=round(ev_draw, 4),
        ev_away=round(ev_away, 4),
        best_value_side=best_value_side,
        best_ev=round(best_ev, 4),
        home_odds_deviation=round(dev_home, 4),
        draw_odds_deviation=round(dev_draw, 4),
        away_odds_deviation=round(dev_away, 4),
        payout_analysis=payout_analysis,
        ev_confidence_penalty=round(penalty, 4),
        notes=notes,
    )


def _high_odds_discount(odds: float, cfg: PricingConfig) -> float:
    """高赔率 EV 折扣系数 (#14)"""
    if odds > cfg.high_odds_ceiling:
        excess = odds - cfg.high_odds_ceiling
        discount = max(0.2, 1.0 - excess * 0.05)
        return discount
    return 1.0


def _analyze_payout(home: float, draw: float, away: float, dh: float, dd: float, da: float) -> str:
    raw = 1 / home + 1 / draw + 1 / away
    payout = 1 / raw
    parts = [f"返还率: {payout:.1%}"]
    if dh > 0.05:
        parts.append(f"主胜偏高 {dh:+.1%}")
    elif dh < -0.05:
        parts.append(f"主胜偏低 {dh:+.1%}")
    if dd > 0.05:
        parts.append(f"平赔偏高 {dd:+.1%}")
    if da > 0.05:
        parts.append(f"客胜偏高 {da:+.1%}")
    return " | ".join(parts)
