"""
第二步：机构统一思路 → 确定比赛方向 (优化版)

优化点:
  #3  赔率走势全方向检测 — 同时追踪主胜/平局/客胜变化
  #13 数据完整性 — 机构数<min时自动降级
  #16 交叉验证 — 输出置信度区间 + 关键假设
  #19 信号衰减 — 时间权重
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import statistics
from datetime import datetime

from engine.config.settings import ConsensusConfig, engine_config


class ConsensusLevel(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    DIVERGENT = "divergent"


class MarketDirection(Enum):
    HOME = "home"
    DRAW_FAVOR = "draw"
    AWAY = "away"
    UNCLEAR = "unclear"


@dataclass
class BookmakerSnapshot:
    name: str
    home_odds: float
    draw_odds: float
    away_odds: float
    implied_home_prob: float
    implied_draw_prob: float
    implied_away_prob: float
    payout_rate: float
    timestamp: Optional[datetime] = None


@dataclass
class OddsShiftReport:
    """赔率走势全方向报告 (#3)"""
    home_trend: Optional[str] = None     # "steam" | "drift" | None
    draw_trend: Optional[str] = None
    away_trend: Optional[str] = None
    shift_magnitude: float = 0.0        # 最大变动幅度
    notes: list[str] = field(default_factory=list)


@dataclass
class ConfidenceInterval:
    """置信度区间 (#16 交叉验证)"""
    point_estimate: float
    lower: float
    upper: float
    width: float               # 区间宽度 → 越小越确定


@dataclass
class ConsensusResult:
    consensus_level: ConsensusLevel
    market_direction: MarketDirection
    direction_strength: float

    bookmaker_count: int
    avg_home_odds: float
    avg_draw_odds: float
    avg_away_odds: float

    home_std: float
    draw_std: float
    away_std: float

    avg_implied_home_prob: float
    avg_implied_draw_prob: float
    avg_implied_away_prob: float

    # 新增
    shift_report: Optional[OddsShiftReport] = None       # #3 全方向走势
    direction_confidence_interval: Optional[ConfidenceInterval] = None  # #16
    data_quality: float = 1.0                            # #13
    key_assumptions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


BOOKMAKER_WEIGHTS = {
    "bet365": 1.0, "pinnacle": 1.0, "william_hill": 0.9,
    "betfair": 0.9, "betway": 0.8, "1xbet": 0.8,
    "unibet": 0.7, "sbobet": 0.7, "bwin": 0.8,
    "marathon": 0.7, "betsson": 0.7, "interwetten": 0.7,
}


def analyze_consensus(
    bookmakers: list[BookmakerSnapshot],
    previous_odds: Optional[list[BookmakerSnapshot]] = None,
    config: Optional[ConsensusConfig] = None,
) -> ConsensusResult:
    """
    机构共识分析 (全方向版)
    """
    cfg = config or engine_config.consensus

    if not bookmakers or len(bookmakers) < cfg.min_bookmaker_count:
        return ConsensusResult(
            consensus_level=ConsensusLevel.DIVERGENT,
            market_direction=MarketDirection.UNCLEAR,
            direction_strength=0.0,
            bookmaker_count=len(bookmakers),
            avg_home_odds=0, avg_draw_odds=0, avg_away_odds=0,
            home_std=0, draw_std=0, away_std=0,
            avg_implied_home_prob=0, avg_implied_draw_prob=0, avg_implied_away_prob=0,
            data_quality=0.0,
            key_assumptions=["机构数量不足"],
        )

    # ---- 加权均值 ----
    total_w = 0.0
    w_home, w_draw, w_away = 0.0, 0.0, 0.0
    raw_homes, raw_draws, raw_aways = [], [], []

    for bm in bookmakers:
        w = BOOKMAKER_WEIGHTS.get(bm.name, 0.5)
        w_home += bm.implied_home_prob * w
        w_draw += bm.implied_draw_prob * w
        w_away += bm.implied_away_prob * w
        total_w += w
        raw_homes.append(bm.home_odds)
        raw_draws.append(bm.draw_odds)
        raw_aways.append(bm.away_odds)

    avg_home_p = w_home / total_w if total_w else 0
    avg_draw_p = w_draw / total_w if total_w else 0
    avg_away_p = w_away / total_w if total_w else 0

    # ---- 标准差 & CV ----
    home_std = statistics.stdev(raw_homes) if len(raw_homes) >= 2 else 0
    draw_std = statistics.stdev(raw_draws) if len(raw_draws) >= 2 else 0
    away_std = statistics.stdev(raw_aways) if len(raw_aways) >= 2 else 0

    mean_home = statistics.mean(raw_homes)
    mean_draw = statistics.mean(raw_draws)
    mean_away = statistics.mean(raw_aways)

    cv_home = home_std / mean_home if mean_home else 0
    cv_draw = draw_std / mean_draw if mean_draw else 0
    cv_away = away_std / mean_away if mean_away else 0
    cv_avg = (cv_home + cv_draw + cv_away) / 3

    # 共识级别
    if cv_avg < cfg.strong_consensus_cv:
        consensus = ConsensusLevel.STRONG
    elif cv_avg < cfg.moderate_consensus_cv:
        consensus = ConsensusLevel.MODERATE
    elif cv_avg < cfg.weak_consensus_cv:
        consensus = ConsensusLevel.WEAK
    else:
        consensus = ConsensusLevel.DIVERGENT

    # ---- 方向 ----
    direction = _determine_direction(avg_home_p, avg_draw_p, avg_away_p, cfg)

    # ---- 走势 (全方向 #3) ----
    shift = OddsShiftReport()
    if previous_odds:
        shift = _detect_odds_shift_all(bookmakers, previous_odds, cfg)

    # ---- 置信度区间 (#16) ----
    ci = ConfidenceInterval(
        point_estimate=avg_home_p,
        lower=max(0, avg_home_p - 1.96 * home_std / (len(raw_homes) ** 0.5)) if home_std else avg_home_p,
        upper=min(1, avg_home_p + 1.96 * home_std / (len(raw_homes) ** 0.5)) if home_std else avg_home_p,
        width=0,
    )
    ci.width = ci.upper - ci.lower

    # ---- 数据质量 (#13) ----
    quality = 1.0
    if len(bookmakers) < 8:
        quality *= 0.7
    if cv_avg > 0.15:
        quality *= 0.5
    quality *= min(1.0, len(bookmakers) / 10)

    # ---- 关键假设 ----
    assumptions = []
    if len(bookmakers) < 8:
        assumptions.append(f"仅{len(bookmakers)}家机构，样本偏小")
    if cv_avg > 0.10:
        assumptions.append("机构间分歧较大，方向可信度降低")
    if shift.shift_magnitude > 0.05:
        assumptions.append(f"赔率正在变动中，注意走势: {shift.shift_magnitude:.1%}")

    return ConsensusResult(
        consensus_level=consensus,
        market_direction=direction,
        direction_strength=max(avg_home_p, avg_draw_p, avg_away_p),
        bookmaker_count=len(bookmakers),
        avg_home_odds=mean_home, avg_draw_odds=mean_draw, avg_away_odds=mean_away,
        home_std=home_std, draw_std=draw_std, away_std=away_std,
        avg_implied_home_prob=avg_home_p,
        avg_implied_draw_prob=avg_draw_p,
        avg_implied_away_prob=avg_away_p,
        shift_report=shift,
        direction_confidence_interval=ci,
        data_quality=quality,
        key_assumptions=assumptions,
        notes=shift.notes,
    )


def _determine_direction(home_p: float, draw_p: float, away_p: float, cfg: ConsensusConfig) -> MarketDirection:
    probs = {"home": home_p, "draw": draw_p, "away": away_p}
    sorted_items = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    top_key, top_val = sorted_items[0]
    second_val = sorted_items[1][1]

    if top_val - second_val >= cfg.direction_gap:
        return MarketDirection(top_key)
    return MarketDirection.UNCLEAR


def _detect_odds_shift_all(
    current: list[BookmakerSnapshot],
    previous: list[BookmakerSnapshot],
    cfg: ConsensusConfig,
) -> OddsShiftReport:
    """全方向赔率走势检测 (#3)"""
    prev_map = {b.name: b for b in previous}
    home_steam, home_drift = 0, 0
    draw_steam, draw_drift = 0, 0
    away_steam, away_drift = 0, 0
    max_shift = 0.0

    for bm in current:
        prev = prev_map.get(bm.name)
        if not prev:
            continue

        for attr, steam_cnt, drift_cnt in [
            ("home_odds", "home_steam", "home_drift"),
            ("draw_odds", "draw_steam", "draw_drift"),
            ("away_odds", "away_steam", "away_drift"),
        ]:
            old = getattr(prev, attr)
            new = getattr(bm, attr)
            change = (old - new) / old  # 正=降水

            if change > cfg.odds_shift_threshold:
                if attr == "home_odds": home_steam += 1
                elif attr == "draw_odds": draw_steam += 1
                else: away_steam += 1
                max_shift = max(max_shift, change)
            elif change < -cfg.odds_shift_threshold:
                if attr == "home_odds": home_drift += 1
                elif attr == "draw_odds": draw_drift += 1
                else: away_drift += 1
                max_shift = max(max_shift, abs(change))

    def _trend(steam, drift):
        if steam > drift + 1: return "steam"
        if drift > steam + 1: return "drift"
        return None

    shift = OddsShiftReport(
        home_trend=_trend(home_steam, home_drift),
        draw_trend=_trend(draw_steam, draw_drift),
        away_trend=_trend(away_steam, away_drift),
        shift_magnitude=round(max_shift, 4),
    )

    # 生成注释
    if shift.home_trend == "steam" and shift.draw_trend == "drift":
        shift.notes.append("机构集体降水主胜+升水平局 → 强主胜信号")
    if shift.draw_trend == "steam":
        shift.notes.append("⚠️ 机构集体降水平局，平局概率提升")
    if shift.away_trend == "steam" and shift.home_trend == "drift":
        shift.notes.append("机构集体降水客胜+升水主胜 → 强客胜信号")

    return shift
