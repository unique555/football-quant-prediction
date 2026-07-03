"""
第一步：基本面 + 盘赔组合 → 判断比赛类型 (优化版)

优化点:
  #1  客队视角支持 — 自动检测强势方并适配
  #2  所有参数参与逻辑 — form_score, key_absence_away 全部接入
  #11 规则矩阵盲区补全 — 连续覆盖无遗漏
  #14 高赔率场景特殊处理
  #17 赛事阶段维度 (联赛初期/中段/冲刺/保级)
  #19 信号衰减机制 (距比赛时间越近权重越高)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from engine.config.settings import ClassifierConfig, engine_config


class MatchType(Enum):
    STRONG_FAVORITE = "strong_favorite"
    MODERATE_FAVORITE = "moderate_favorite"
    EVEN_CONTEST = "even_contest"
    UPSET_RISK = "upset_risk"
    DERBY_SPECIAL = "derby_special"
    VALUE_TRAP = "value_trap"


class MatchPhase(Enum):
    """赛事阶段 — #17"""

    EARLY = "early"  # 前 5 轮
    MID = "mid"  # 中段
    CRUNCH = "crunch"  # 冲刺期 (最后 8 轮)
    RELEGATION_CLASH = "relegation"  # 保级直接对话
    TITLE_DECIDER = "title"  # 争冠关键战
    CUP_KNOCKOUT = "cup_ko"  # 杯赛淘汰赛
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    match_type: MatchType
    match_phase: MatchPhase = MatchPhase.UNKNOWN
    confidence: float = 0.0
    reason: str = ""

    # 基本面
    tsi_home: float = 0.0
    tsi_away: float = 0.0
    tsi_gap: float = 0.0
    favorite_side: str = "home"  # "home" | "away" | "none"

    # 盘赔
    asian_handicap: Optional[float] = None
    home_odds: Optional[float] = None
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    odds_movement: Optional[str] = None

    # 状态
    home_form_score: float = 0.5
    away_form_score: float = 0.5
    key_absences: int = 0  # 强势方关键缺阵人数

    # 标记
    subtype_flags: list[str] = field(default_factory=list)
    phase_impact: str = ""  # #17 赛事阶段对方向的影响


# 德比关键词
DERBY_KEYWORDS = [
    "德比",
    "derby",
    "classico",
    "classic",
    "德比战",
    "同城",
    "国家德比",
    "rivalry",
    "曼市德比",
    "北伦敦德比",
    "马德里德比",
    "米兰德比",
]


# ============================================================
# 核心: 双方向对称分类
# ============================================================


def classify_match(
    tsi_home: float,
    tsi_away: float,
    asian_handicap: Optional[float] = None,
    initial_odds: Optional[tuple[float, float, float]] = None,
    odds_movement: Optional[str] = None,
    is_derby: bool = False,
    home_form_score: float = 0.5,
    away_form_score: float = 0.5,
    key_absence_home: int = 0,
    key_absence_away: int = 0,
    match_date: Optional[datetime] = None,
    league_round: int = 20,
    total_rounds: int = 38,
    home_position: int = 10,
    away_position: int = 10,
) -> ClassificationResult:
    """
    比赛分类 (双向对称)

    核心改进 #1: 不再假设主队=强队。
    先判定「强势方」再分类，所有逻辑以强势方视角运行。
    """
    cfg = engine_config.classifier

    # ---- 0. 判定强势方 ----
    tsi_gap = tsi_home - tsi_away
    abs_gap = abs(tsi_gap)
    if tsi_gap > 5:
        favorite = "home"
        fav_absence, dog_absence = key_absence_home, key_absence_away
        fav_form, dog_form = home_form_score, away_form_score
        sig = 1
    elif tsi_gap < -5:
        favorite = "away"
        fav_absence, dog_absence = key_absence_away, key_absence_home
        fav_form, dog_form = away_form_score, home_form_score
        sig = -1
    else:
        favorite = "none"
        fav_absence, dog_absence = max(key_absence_home, key_absence_away), 0
        fav_form, dog_form = 0.5, 0.5
        sig = 0

    # ---- 1. 德比 ----
    if is_derby:
        return ClassificationResult(
            match_type=MatchType.DERBY_SPECIAL,
            match_phase=_detect_phase(league_round, total_rounds, home_position, away_position),
            confidence=0.85 - cfg.derby_confidence_penalty,
            reason="德比战：基本面参考权重降低，战意因素主导",
            tsi_home=tsi_home,
            tsi_away=tsi_away,
            tsi_gap=tsi_gap,
            favorite_side=favorite,
            asian_handicap=asian_handicap,
            home_form_score=home_form_score,
            away_form_score=away_form_score,
            key_absences=fav_absence,
        )

    # ---- 2. 亚盘归一化 (转为强势方视角) ----
    fav_handicap = _normalize_handicap(asian_handicap, sig) if asian_handicap is not None else None

    # ---- 3. 规则匹配 (连续覆盖，解决 #11) ----
    matched_type = _match_rule_continuous(abs_gap, fav_handicap, cfg)

    # ---- 4. 冷门风险检测 (双向) ----
    risk_flags, form_risk = _detect_upset_flags_v2(
        abs_gap=abs_gap,
        fav_handicap=fav_handicap,
        odds_movement=odds_movement,
        fav_absence=fav_absence,
        dog_absence=dog_absence,
        fav_form=fav_form,
        dog_form=dog_form,
        cfg=cfg,
    )

    # ---- 5. 价值陷阱检测 ----
    trap_flags = _detect_value_trap_v2(
        abs_gap=abs_gap,
        fav_handicap=fav_handicap,
        initial_odds=initial_odds,
        sig=sig,
        cfg=cfg,
    )

    # 只有「严重陷阱」才直接跳过，其他陷阱信号只做警告
    severe_traps = {"low_odds_deep_handicap_mismatch", "high_odds_deep_handicap_anomaly"}
    if any(f in severe_traps for f in trap_flags):
        matched_type = MatchType.VALUE_TRAP

    # ---- 6. 赛事阶段 ----
    phase = _detect_phase(league_round, total_rounds, home_position, away_position)
    phase_impact = _phase_impact(phase, matched_type)

    # ---- 7. 信号衰减 (距比赛时间) ----
    decay = _time_decay(match_date)

    # ---- 8. 组装 ----
    confidence = _compute_confidence_v2(
        matched_type,
        abs_gap,
        fav_handicap,
        risk_flags,
        trap_flags,
        decay,
        cfg,
    )

    return ClassificationResult(
        match_type=matched_type,
        match_phase=phase,
        confidence=confidence,
        reason=_generate_reason_v2(
            matched_type, favorite, abs_gap, risk_flags, trap_flags, form_risk
        ),
        subtype_flags=risk_flags + trap_flags + ([form_risk] if form_risk else []),
        tsi_home=tsi_home,
        tsi_away=tsi_away,
        tsi_gap=tsi_gap,
        favorite_side=favorite,
        asian_handicap=asian_handicap,
        home_odds=initial_odds[0] if initial_odds else None,
        draw_odds=initial_odds[1] if initial_odds else None,
        away_odds=initial_odds[2] if initial_odds else None,
        odds_movement=odds_movement,
        home_form_score=home_form_score,
        away_form_score=away_form_score,
        key_absences=fav_absence,
        phase_impact=phase_impact,
    )


# ============================================================
# 连续规则匹配 (#11 修复)
# ============================================================


def _match_rule_continuous(
    abs_gap: float,
    fav_handicap: Optional[float],
    cfg: ClassifierConfig,
) -> MatchType:
    """连续规则矩阵 — 无盲区"""

    if fav_handicap is None:
        # 仅有 TSI，无亚盘
        if abs_gap >= cfg.strong_favorite_tsi_gap:
            return MatchType.STRONG_FAVORITE
        elif abs_gap >= cfg.moderate_favorite_tsi_gap:
            return MatchType.MODERATE_FAVORITE
        else:
            return MatchType.EVEN_CONTEST

    # 盘口深度 + TSI 差距的交集判断
    if abs_gap >= cfg.strong_favorite_tsi_gap and fav_handicap <= cfg.deep_handicap:
        return MatchType.STRONG_FAVORITE
    elif abs_gap >= cfg.moderate_favorite_tsi_gap and fav_handicap <= cfg.moderate_handicap:
        return MatchType.MODERATE_FAVORITE
    elif fav_handicap <= cfg.deep_handicap and abs_gap < cfg.strong_favorite_tsi_gap:
        # 深盘但 TSI 不足 = 危险
        return MatchType.UPSET_RISK
    elif abs_gap <= cfg.even_contest_max_gap:
        return MatchType.EVEN_CONTEST
    else:
        # 兜底: 有差距但不极端
        return MatchType.MODERATE_FAVORITE


# ============================================================
# 冷门风险 v2 — 接入 form_score & key_absence_away (#2)
# ============================================================


def _detect_upset_flags_v2(
    abs_gap: float,
    fav_handicap: Optional[float],
    odds_movement: Optional[str],
    fav_absence: int,
    dog_absence: int,
    fav_form: float,
    dog_form: float,
    cfg: ClassifierConfig,
) -> tuple[list[str], Optional[str]]:
    """扩展版冷门检测"""
    flags = []
    form_risk = None

    # 强队浅盘
    if (
        abs_gap >= cfg.upset_tsi_threshold
        and fav_handicap is not None
        and fav_handicap > cfg.upset_shallow_handicap
    ):
        flags.append("strong_team_shallow_handicap")

    # 赔率漂移
    if odds_movement == "drifting":
        flags.append("odds_drifting_out")

    # 强势方关键伤缺 (双向)
    if fav_absence >= cfg.key_absence_alert:
        flags.append("favorite_key_players_absent")

    # 弱势方全员健康 + 强势方缺人 = 加倍风险
    if fav_absence >= 1 and dog_absence == 0:
        flags.append("asymmetric_squad_advantage")

    # 状态反转 (#2: form_score 终于接入)
    if dog_form > fav_form + 0.25:
        flags.append("form_reversal")
        form_risk = "dog_in_form"
    elif fav_form < 0.30 and dog_form > 0.50:
        flags.append("favorite_out_of_form")

    # 单边受热 + 浅盘
    if (
        odds_movement == "steaming"
        and fav_handicap is not None
        and fav_handicap > cfg.upset_shallow_handicap
    ):
        flags.append("overheated_with_shallow_line")

    return flags, form_risk


# ============================================================
# 价值陷阱 v2 — 高赔率特殊处理 (#14)
# ============================================================


def _detect_value_trap_v2(
    abs_gap: float,
    fav_handicap: Optional[float],
    initial_odds: Optional[tuple[float, float, float]],
    sig: int,
    cfg: ClassifierConfig,
) -> list[str]:
    """扩展版陷阱检测"""
    flags = []

    if not initial_odds or fav_handicap is None:
        return flags

    ho, do, ao = initial_odds

    # 主队视角赔率
    fav_odds = ho if sig >= 0 else ao

    # 低赔 + 深盘 + 实力不足 = 陷阱
    if (
        fav_odds < cfg.trap_low_odds
        and fav_handicap <= cfg.trap_handicap_threshold
        and abs_gap < cfg.trap_tsi_gap_max
    ):
        flags.append("low_odds_deep_handicap_mismatch")

    # 高赔率 + 深盘 (#14)
    if fav_odds > 3.0 and fav_handicap < -0.5:
        flags.append("high_odds_deep_handicap_anomaly")

    # 平赔极低 (< 3.0) + 强弱分明
    if do < 3.0 and abs_gap > 15:
        flags.append("suspicious_low_draw_odds")

    # 返还率异常 (< 98% 或 > 118%)
    raw = 1 / ho + 1 / do + 1 / ao
    if raw > 1.18 or raw < 1.02:
        flags.append("abnormal_payout_rate")

    return flags


# ============================================================
# 赛事阶段检测 (#17)
# ============================================================


def _detect_phase(
    league_round: int,
    total_rounds: int,
    home_pos: int,
    away_pos: int,
) -> MatchPhase:
    """赛事阶段判定"""
    progress = league_round / max(total_rounds, 1)

    if progress <= 0.15:
        phase = MatchPhase.EARLY
    elif progress >= 0.80:
        # 最后 8 轮: 可能争冠/保级
        if (home_pos <= 3 or away_pos <= 3) and (
            home_pos >= total_rounds - 6 or away_pos >= total_rounds - 6
        ):
            phase = MatchPhase.CRUNCH
        elif abs(home_pos - away_pos) <= 3 and (
            home_pos >= total_rounds - 6 or away_pos >= total_rounds - 6
        ):
            phase = MatchPhase.RELEGATION_CLASH
        else:
            phase = MatchPhase.CRUNCH
    else:
        phase = MatchPhase.MID

    return phase


def _phase_impact(phase: MatchPhase, match_type: MatchType) -> str:
    """赛事阶段对预测的影响"""
    impacts = {
        MatchPhase.EARLY: "赛季初期，数据样本不足，降低模型权重",
        MatchPhase.RELEGATION_CLASH: "保级直接对话，战意主导，平局概率提升",
        MatchPhase.TITLE_DECIDER: "争冠关键战，谨慎对待浅盘让球方",
        MatchPhase.CUP_KNOCKOUT: "杯赛淘汰赛，平局概率降低，加时预期",
        MatchPhase.CRUNCH: "赛季冲刺期，强队稳定性下降",
    }
    return impacts.get(phase, "")


# ============================================================
# 信号衰减 (#19)
# ============================================================


def _time_decay(match_date: Optional[datetime]) -> float:
    """距比赛时间越近→权重越高"""
    if match_date is None:
        return 0.8
    hours_left = (match_date - datetime.now()).total_seconds() / 3600
    half_life = engine_config.synthesis.decay_hours_halflife
    decay = 2 ** (-hours_left / half_life) if hours_left > 0 else 1.0
    return min(max(decay, 0.3), 1.0)


# ============================================================
# 辅助
# ============================================================


def _normalize_handicap(asian_handicap: Optional[float], sig: int) -> Optional[float]:
    """亚盘转为强势方视角"""
    if asian_handicap is None:
        return None
    if sig >= 0:
        return asian_handicap
    else:
        return -asian_handicap


def _compute_confidence_v2(
    match_type: MatchType,
    abs_gap: float,
    fav_handicap: Optional[float],
    risk_flags: list[str],
    trap_flags: list[str],
    decay: float,
    cfg: ClassifierConfig,
) -> float:
    """增强版置信度"""
    base = 0.70

    if abs_gap > 15:
        base += 0.15
    if fav_handicap is not None and abs(fav_handicap) > 0.5:
        base += 0.10
    if match_type == MatchType.DERBY_SPECIAL:
        base -= cfg.derby_confidence_penalty
    if risk_flags:
        base -= 0.05 * len(risk_flags)
    if trap_flags:
        base -= 0.10 * len(trap_flags)
    base *= decay

    return max(min(base, 0.95), 0.10)


def _generate_reason_v2(
    match_type: MatchType,
    favorite: str,
    abs_gap: float,
    risk_flags: list[str],
    trap_flags: list[str],
    form_risk: Optional[str],
) -> str:
    """生成可解释理由"""
    fav_label = "主队" if favorite == "home" else ("客队" if favorite == "away" else "双方")

    reasons = {
        MatchType.STRONG_FAVORITE: f"{fav_label}实力占优，TSI差距{abs_gap:.0f}，深盘支撑",
        MatchType.MODERATE_FAVORITE: f"{fav_label}稍占上风，TSI差距{abs_gap:.0f}，盘口适中",
        MatchType.EVEN_CONTEST: f"实力接近，TSI差距仅{abs_gap:.0f}",
        MatchType.UPSET_RISK: f"{fav_label}有隐患，盘赔与基本面不匹配",
        MatchType.DERBY_SPECIAL: "德比/特殊战意，基本面参考权重降低",
        MatchType.VALUE_TRAP: "赔率与基本面明显偏离，疑似价值陷阱",
    }

    base = reasons.get(match_type, "未知")
    parts = []

    if risk_flags:
        parts.append(f"风险: {', '.join(risk_flags)}")
    if form_risk:
        parts.append(f"状态: {form_risk}")
    if trap_flags:
        parts.append(f"陷阱: {', '.join(trap_flags)}")

    if parts:
        base += " | " + " | ".join(parts)

    return base
