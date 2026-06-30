"""
第三步：指数辅助 → 核实方向 (优化版)

优化点:
  #4  赔率稳定性归一化修复 — 使用 CV (变异系数) 而非裸 std
  #16 交叉验证 — 验证结果附置信度
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from engine.config.settings import ValidatorConfig, engine_config


class ValidationVerdict(Enum):
    CONFIRMED = "confirmed"
    NEUTRAL = "neutral"
    CONTRADICT = "contradict"
    INSUFFICIENT = "insufficient"


@dataclass
class KellyResult:
    home_kelly: float
    draw_kelly: float
    away_kelly: float
    verdict: str
    confidence: float = 0.5


@dataclass
class VolumeResult:
    home_volume_pct: float
    draw_volume_pct: float
    away_volume_pct: float
    hot_side: Optional[str]
    is_overheated: bool
    verdict: str


@dataclass
class ValidationResult:
    verdict: ValidationVerdict
    kelly: Optional[KellyResult] = None
    volume: Optional[VolumeResult] = None
    odds_stability: Optional[float] = None  # 归一化稳定性 (CV法)
    draw_signal: Optional[bool] = None
    support_score: float = 0.0
    notes: list[str] = field(default_factory=list)


def validate_with_indexes(
    direction: str,
    avg_home_odds: float,
    avg_draw_odds: float,
    avg_away_odds: float,
    home_std: float,
    draw_std: float,
    away_std: float,
    home_volume_pct: Optional[float] = None,
    draw_volume_pct: Optional[float] = None,
    away_volume_pct: Optional[float] = None,
    config: Optional[ValidatorConfig] = None,
) -> ValidationResult:
    """
    指数验证 (稳定性归一化版)
    """
    cfg = config or engine_config.validator
    notes = []
    support = 0.0

    # ---- 1. 凯利 ----
    kelly = _compute_kelly(avg_home_odds, avg_draw_odds, avg_away_odds, direction, cfg)
    if kelly:
        if f"{direction}_value" in kelly.verdict:
            support += cfg.kelly_support_weight
            notes.append(f"凯利支持{direction}方向")
        else:
            support += cfg.kelly_against_weight
            notes.append(f"凯利不指向{direction}方向")

    # ---- 2. 成交量 ----
    volume = None
    if all(v is not None for v in [home_volume_pct, draw_volume_pct, away_volume_pct]):
        volume = _analyze_volume(home_volume_pct, draw_volume_pct, away_volume_pct, cfg)
        if volume.is_overheated and volume.hot_side == direction:
            support += cfg.overheat_penalty
            notes.append(f"⚠️ {direction}方向过热 ({volume.hot_volume_pct():.0%})")
        elif not volume.is_overheated and volume.hot_side == direction:
            support += cfg.volume_support
            notes.append("市场热度与方向一致")

    # ---- 3. 稳定性 (#4 修复: 用 CV 而非裸 std) ----
    means = [avg_home_odds, avg_draw_odds, avg_away_odds]
    stds = [home_std, draw_std, away_std]
    cvs = [s / m if m > 0 else 0 for s, m in zip(stds, means)]
    avg_cv = sum(cvs) / 3

    # 稳定性 = 1 - 归一化 CV (CV=0.2 基本算不稳定)
    stability = 1.0 - min(avg_cv / 0.20, 1.0)

    if stability > cfg.stability_high:
        support += cfg.stability_reward
        notes.append("赔率结构稳定")
    elif stability < cfg.stability_low:
        support += cfg.stability_penalty
        notes.append("⚠️ 赔率波动大，方向可信度降低")

    # ---- 4. 平局信号 ----
    draws_are_low = _detect_draw_signal(avg_draw_odds, avg_home_odds, avg_away_odds, cfg)
    if draws_are_low and direction != "draw":
        support += cfg.draw_signal_penalty
        notes.append("平赔偏低，关注平局可能")

    # ---- 5. 综合 ----
    if support >= cfg.confirmed_score:
        verdict = ValidationVerdict.CONFIRMED
    elif support >= cfg.neutral_min:
        verdict = ValidationVerdict.NEUTRAL
    elif support >= cfg.contradict_min:
        verdict = ValidationVerdict.CONTRADICT
    else:
        verdict = ValidationVerdict.INSUFFICIENT

    return ValidationResult(
        verdict=verdict,
        kelly=kelly,
        volume=volume,
        odds_stability=stability,
        draw_signal=draws_are_low,
        support_score=support,
        notes=notes,
    )


def _compute_kelly(
    avg_home_odds: float,
    avg_draw_odds: float,
    avg_away_odds: float,
    direction: str,
    cfg: ValidatorConfig,
) -> Optional[KellyResult]:
    if not all([avg_home_odds > 0, avg_draw_odds > 0, avg_away_odds > 0]):
        return None

    raw_h, raw_d, raw_a = 1 / avg_home_odds, 1 / avg_draw_odds, 1 / avg_away_odds
    total = raw_h + raw_d + raw_a

    fair_h, fair_d, fair_a = raw_h / total, raw_d / total, raw_a / total

    k_h = max((avg_home_odds * fair_h - 1) / (avg_home_odds - 1), -1)
    k_d = max((avg_draw_odds * fair_d - 1) / (avg_draw_odds - 1), -1)
    k_a = max((avg_away_odds * fair_a - 1) / (avg_away_odds - 1), -1)

    kelly_map = {"home": k_h, "draw": k_d, "away": k_a}
    best = max(kelly_map, key=kelly_map.get)

    return KellyResult(
        home_kelly=round(k_h, 4),
        draw_kelly=round(k_d, 4),
        away_kelly=round(k_a, 4),
        verdict=f"{best}_value",
    )


def _analyze_volume(
    home_pct: float,
    draw_pct: float,
    away_pct: float,
    cfg: ValidatorConfig,
) -> VolumeResult:
    vol_map = {"home": home_pct, "draw": draw_pct, "away": away_pct}
    hot = max(vol_map, key=vol_map.get)
    hot_val = vol_map[hot]
    is_over = hot_val > cfg.overheat_threshold

    result = VolumeResult(
        home_volume_pct=home_pct,
        draw_volume_pct=draw_pct,
        away_volume_pct=away_pct,
        hot_side=hot,
        is_overheated=is_over,
        verdict="overheated" if is_over else "balanced",
    )
    # monkey-patch helper
    result.hot_volume_pct = lambda: hot_val  # type: ignore
    return result


def _detect_draw_signal(
    draw_odds: float,
    home_odds: float,
    away_odds: float,
    cfg: ValidatorConfig,
) -> bool:
    if not all([draw_odds > 0, home_odds > 0, away_odds > 0]):
        return False
    return draw_odds < min(home_odds, away_odds) + cfg.draw_signal_threshold
