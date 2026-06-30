"""
第五步：综合判断 — 五步法总编排 (全优化版)

优化点聚合:
  #5  CLV 追踪接入
  #6  亚盘分析接入
  #7  进球预测接入 (via ML 模型概率)
  #8  仓位管理接入
  #9  联赛特异性校准接入
  #10 反馈闭环接入 (赛后)
  #16 交叉验证 — 各步骤间置信度区间传递
  #17 赛事阶段维度
  #19 信号衰减
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime

from engine.config.settings import engine_config, SynthesisConfig
from engine.classifier.match_classifier import (
    classify_match, MatchType, MatchPhase, ClassificationResult,
)
from engine.consensus.consensus_analyzer import (
    analyze_consensus, ConsensusLevel, MarketDirection,
    ConsensusResult, BookmakerSnapshot,
)
from engine.validator.index_validator import (
    validate_with_indexes, ValidationVerdict, ValidationResult,
)
from engine.pricing.pricing_checker import (
    check_market_pricing, PricingVerdict, PricingResult,
)
from engine.clv.clv_tracker import (
    analyze_clv, CLVResult, OddsSnapshot,
)
from engine.asian.asian_analyzer import (
    analyze_asian_handicap, AsianResult, AsianLine,
)
from engine.sizing.position_sizer import (
    calculate_kelly, scene_adjusted_kelly, PositionSizingResult,
)
from engine.calibration.league_calibrator import (
    calibrate_by_league, CalibratedProbabilities, get_league_priors,
)
from engine.input_validator import (
    validate_classification_input, validate_consensus_input,
    validate_odds_sanity,
)
from engine.feedback.prediction_feedback import PredictionRecord


class FinalVerdict(Enum):
    HIGH_CONFIDENCE = "high_confidence"
    MODERATE_CONFIDENCE = "moderate"
    LOW_CONFIDENCE = "low_confidence"
    NO_EDGE = "no_edge"
    SKIP = "skip"


@dataclass
class StepReport:
    step: int
    name: str
    conclusion: str
    confidence: float = 1.0       # 该步骤自身置信度
    data_quality: float = 1.0     # 数据质量
    details: dict = field(default_factory=dict)


@dataclass
class FinalReport:
    # 比赛
    home_team: str = ""
    away_team: str = ""
    league: str = ""
    match_date: Optional[datetime] = None

    # 五步结论
    classification: Optional[ClassificationResult] = None
    consensus: Optional[ConsensusResult] = None
    validation: Optional[ValidationResult] = None
    pricing: Optional[PricingResult] = None

    # 新增模块
    clv: Optional[CLVResult] = None                 # #5
    asian: Optional[AsianResult] = None              # #6
    calibrated_probs: Optional[CalibratedProbabilities] = None  # #9

    # 仓位
    position_sizing: Optional[PositionSizingResult] = None  # #8
    raw_kelly_fraction: float = 0.0

    # 最终判定
    final_verdict: FinalVerdict = FinalVerdict.NO_EDGE
    recommended_direction: Optional[str] = None
    confidence_score: float = 0.0

    # 概率
    final_home_prob: float = 0.33
    final_draw_prob: float = 0.34
    final_away_prob: float = 0.33

    # 报告
    step_reports: list[StepReport] = field(default_factory=list)
    cross_validation: list[str] = field(default_factory=list)   # #16
    summary: str = ""
    warnings: list[str] = field(default_factory=list)


# ============================================================
# 总编排
# ============================================================

def run_full_pipeline(
    home_team: str,
    away_team: str,
    league: str = "",
    # Step 1
    tsi_home: float = 50, tsi_away: float = 50,
    asian_handicap: Optional[float] = None,
    initial_odds: Optional[tuple[float, float, float]] = None,
    odds_movement: Optional[str] = None,
    is_derby: bool = False,
    home_form_score: float = 0.5, away_form_score: float = 0.5,
    key_absence_home: int = 0, key_absence_away: int = 0,
    match_date: Optional[datetime] = None,
    league_round: int = 20, total_rounds: int = 38,
    home_position: int = 10, away_position: int = 10,
    # Step 2
    bookmaker_snapshots: Optional[list[BookmakerSnapshot]] = None,
    previous_bookmakers: Optional[list[BookmakerSnapshot]] = None,
    # Step 3
    home_volume_pct: Optional[float] = None,
    draw_volume_pct: Optional[float] = None,
    away_volume_pct: Optional[float] = None,
    # Step 4
    model_home_prob: Optional[float] = None,
    model_draw_prob: Optional[float] = None,
    model_away_prob: Optional[float] = None,
    best_home_odds: Optional[float] = None,
    best_draw_odds: Optional[float] = None,
    best_away_odds: Optional[float] = None,
    # CLV
    opening_odds: Optional[OddsSnapshot] = None,
    closing_odds: Optional[OddsSnapshot] = None,
    odds_timeseries: Optional[list[OddsSnapshot]] = None,
    # 亚盘
    current_asian_lines: Optional[list[AsianLine]] = None,
    opening_asian_lines: Optional[list[AsianLine]] = None,
    # 总配置
    config: Optional[SynthesisConfig] = None,
) -> FinalReport:
    """
    五步综合判断 (全模块版)
    """
    cfg = config or engine_config.synthesis
    report = FinalReport(
        home_team=home_team, away_team=away_team,
        league=league, match_date=match_date,
    )
    steps: list[StepReport] = []
    xv: list[str] = []  # cross-validation notes

    # ================================================================
    # Step 1: 比赛分类
    # ================================================================
    input_val = validate_classification_input(tsi_home, tsi_away, asian_handicap, initial_odds)
    classification = classify_match(
        tsi_home=tsi_home, tsi_away=tsi_away,
        asian_handicap=asian_handicap, initial_odds=initial_odds,
        odds_movement=odds_movement, is_derby=is_derby,
        home_form_score=home_form_score, away_form_score=away_form_score,
        key_absence_home=key_absence_home, key_absence_away=key_absence_away,
        match_date=match_date, league_round=league_round,
        total_rounds=total_rounds, home_position=home_position,
        away_position=away_position,
    )
    report.classification = classification
    steps.append(StepReport(
        step=1, name="比赛分类",
        conclusion=f"类型: {classification.match_type.value} | "
                   f"强势方: {classification.favorite_side} | "
                   f"阶段: {classification.match_phase.value}",
        confidence=classification.confidence,
        data_quality=input_val.data_quality_score,
        details={
            "match_type": classification.match_type.value,
            "favorite": classification.favorite_side,
            "phase": classification.match_phase.value,
        },
    ))
    if classification.phase_impact:
        steps[-1].conclusion += f" | {classification.phase_impact}"

    # 价值陷阱直接跳过
    if classification.match_type == MatchType.VALUE_TRAP:
        report.final_verdict = FinalVerdict.SKIP
        report.summary = "🚨 检测到价值陷阱信号，建议跳过"
        report.warnings = ["疑似价值陷阱"]
        report.step_reports = steps
        return report

    # ================================================================
    # Step 2: 机构共识
    # ================================================================
    consensus = None
    if bookmaker_snapshots and len(bookmaker_snapshots) >= 3:
        val2 = validate_consensus_input(
            len(bookmaker_snapshots),
            [b.home_odds for b in bookmaker_snapshots],
        )
        consensus = analyze_consensus(bookmaker_snapshots, previous_bookmakers)
        report.consensus = consensus
        steps.append(StepReport(
            step=2, name="机构共识",
            conclusion=f"共识: {consensus.consensus_level.value} | "
                       f"方向: {consensus.market_direction.value} | "
                       f"强度: {consensus.direction_strength:.1%}",
            confidence=1.0 - {"strong": 0, "moderate": 0.15, "weak": 0.35, "divergent": 0.6}.get(
                consensus.consensus_level.value, 0.5),
            data_quality=consensus.data_quality,
            details={"consensus": consensus.consensus_level.value,
                     "direction": consensus.market_direction.value,
                     "cv_avg": round(
                         (consensus.home_std/(consensus.avg_home_odds or 1) +
                          consensus.draw_std/(consensus.avg_draw_odds or 1) +
                          consensus.away_std/(consensus.avg_away_odds or 1)) / 3, 4)},
        ))
        if consensus.shift_report and consensus.shift_report.notes:
            for n in consensus.shift_report.notes:
                if "⚠️" in n:
                    report.warnings.append(n)
    else:
        steps.append(StepReport(step=2, name="机构共识",
                                conclusion="数据不足", confidence=0, data_quality=0))

    # ================================================================
    # Step 3: 指数验证
    # ================================================================
    validation = None
    if consensus and consensus.market_direction.value != "unclear":
        validation = validate_with_indexes(
            direction=consensus.market_direction.value,
            avg_home_odds=consensus.avg_home_odds,
            avg_draw_odds=consensus.avg_draw_odds,
            avg_away_odds=consensus.avg_away_odds,
            home_std=consensus.home_std, draw_std=consensus.draw_std,
            away_std=consensus.away_std,
            home_volume_pct=home_volume_pct,
            draw_volume_pct=draw_volume_pct,
            away_volume_pct=away_volume_pct,
        )
        report.validation = validation
        steps.append(StepReport(
            step=3, name="指数验证",
            conclusion=f"结论: {validation.verdict.value} | "
                       f"支持度: {validation.support_score:+.2f}",
            details={"verdict": validation.verdict.value,
                     "support_score": validation.support_score},
        ))
        if validation.notes:
            for n in validation.notes:
                if "⚠️" in n:
                    report.warnings.append(n)
    else:
        steps.append(StepReport(step=3, name="指数验证",
                                conclusion="无方向数据", confidence=0))

    # ================================================================
    # Step 4: 市场定价
    # ================================================================
    pricing = None
    has_model = all(p is not None for p in [model_home_prob, model_draw_prob, model_away_prob])
    has_market = all(o is not None for o in [best_home_odds, best_draw_odds, best_away_odds])
    if has_model and has_market:
        # 联赛校准 (#9)
        calibrated = calibrate_by_league(
            model_home_prob, model_draw_prob, model_away_prob, league,
        )
        report.calibrated_probs = calibrated

        pricing = check_market_pricing(
            calibrated.home_prob, calibrated.draw_prob, calibrated.away_prob,
            best_home_odds, best_draw_odds, best_away_odds,
        )
        report.pricing = pricing
        steps.append(StepReport(
            step=4, name="市场定价",
            conclusion=f"结论: {pricing.verdict.value} | "
                       f"{'价值: ' + pricing.best_value_side + ' EV=' + f'{pricing.best_ev:.2%}' if pricing.best_value_side else '无价值'}",
            details={"verdict": pricing.verdict.value, "best_ev": pricing.best_ev},
        ))
    else:
        steps.append(StepReport(step=4, name="市场定价",
                                conclusion="缺少模型概率或市场赔率", confidence=0))

    # ================================================================
    # 增强模块: CLV (#5)
    # ================================================================
    if opening_odds and closing_odds:
        clv = analyze_clv(opening_odds, closing_odds, odds_timeseries)
        report.clv = clv
        if clv.clv_direction:
            steps.append(StepReport(
                step="4a", name="CLV追踪",
                conclusion=f"方向: {clv.clv_direction} | 强度: {clv.clv_strength:.1%} | 模式: {clv.pattern}",
            ))

    # ================================================================
    # 增强模块: 亚盘 (#6)
    # ================================================================
    if current_asian_lines:
        asian = analyze_asian_handicap(current_asian_lines, opening_asian_lines)
        report.asian = asian
        if asian.direction_signal:
            steps.append(StepReport(
                step="4b", name="亚盘分析",
                conclusion=f"方向: {asian.direction_signal} | "
                           f"盘口: {asian.main_handicap} | "
                           f"走势: {asian.trend.value}",
            ))

    # ================================================================
    # Step 5: 综合判断 (融合所有信号)
    # ================================================================
    report.step_reports = steps
    # 注入市场赔率到 report (供融合逻辑使用)
    report.__dict__['_market_home_odds'] = best_home_odds
    report.__dict__['_market_draw_odds'] = best_draw_odds
    report.__dict__['_market_away_odds'] = best_away_odds
    _final_synthesis_v2(report, cfg)

    # ================================================================
    # 仓位管理 (#8)
    # ================================================================
    direction_odds_map = {"home": best_home_odds, "draw": best_draw_odds, "away": best_away_odds}
    rec_dir = report.recommended_direction
    if rec_dir and rec_dir in direction_odds_map and direction_odds_map[rec_dir]:
        best_odds = direction_odds_map[rec_dir]
        prob_map = {"home": report.final_home_prob, "draw": report.final_draw_prob, "away": report.final_away_prob}
        raw_size = calculate_kelly(prob_map[rec_dir], best_odds)
        adjusted = scene_adjusted_kelly(
            raw_size.recommended_fraction,
            match_type=classification.match_type.value,
            consensus_level=consensus.consensus_level.value if consensus else "weak",
            is_derby=is_derby,
        )
        raw_size.recommended_fraction = adjusted
        report.position_sizing = raw_size
        report.raw_kelly_fraction = raw_size.kelly_fraction
        steps.append(StepReport(
            step="5a", name="仓位管理",
            conclusion=f"建议仓位: {adjusted:.2%} | {raw_size.sizing_label}",
        ))

    return report


# ============================================================
# 信号融合 (支持 CLV + 亚盘)
# ============================================================

def _final_synthesis_v2(report: FinalReport, cfg: SynthesisConfig):
    """增强版信号融合"""
    cls = report.classification
    con = report.consensus
    val = report.validation
    pri = report.pricing
    clv = report.clv
    asian = report.asian

    signals: list[tuple[str, float, float]] = []  # (方向, 分数, 权重)
    warnings = list(report.warnings)
    xv: list[str] = []

    # ---- Step 1 信号 ----
    if cls:
        if cls.match_type == MatchType.DERBY_SPECIAL:
            warnings.append("⚠️ 德比战：基本面权重降低")
        elif cls.match_type == MatchType.UPSET_RISK:
            warnings.append("⚠️ 冷门风险型，降低仓位")
            signals.append(("against_favorite", 0.6, cfg.weight_classification))
        elif cls.match_type == MatchType.VALUE_TRAP:
            report.final_verdict = FinalVerdict.SKIP
            report.summary = "🚨 价值陷阱，建议跳过"
            return

    # ---- Step 2 共识 ----
    if con and con.market_direction.value != "unclear":
        quality_factor = con.data_quality
        signals.append((con.market_direction.value, con.direction_strength * quality_factor,
                        cfg.weight_consensus))

    # ---- Step 3 验证 ----
    if val:
        if val.verdict == ValidationVerdict.CONFIRMED:
            signals.append(("confirm", val.support_score, cfg.weight_validation))
        elif val.verdict == ValidationVerdict.CONTRADICT:
            warnings.append("⚠️ 指数与机构矛盾")

    # ---- Step 4 定价 ----
    if pri and pri.best_value_side:
        if pri.verdict == PricingVerdict.UNDERVALUED:
            ev_weight = min(abs(pri.best_ev) * 5, 1.0)
            signals.append((pri.best_value_side, ev_weight, cfg.weight_pricing))

    # ---- CLV (#5) ----
    if clv and clv.clv_direction and clv.is_informative:
        signals.append((clv.clv_direction, clv.clv_strength * 0.6, 0.20))
        xv.append(f"CLV指向{clv.clv_direction} (强度{clv.clv_strength:.1%})")

    # ---- 亚盘 (#6) ----
    if asian and asian.direction_signal:
        signals.append((asian.direction_signal, asian.signal_strength * 0.7, 0.15))
        xv.append(f"亚盘指向{asian.direction_signal} (强度{asian.signal_strength:.1%})")

    # ---- 联赛先验 (#9) ----
    if report.league:
        league_prior = get_league_priors(report.league)
        # 用联赛先验做弱平滑
        signals.append(("prior_home", league_prior[0], 0.05))
        signals.append(("prior_draw", league_prior[1], 0.05))
        signals.append(("prior_away", league_prior[2], 0.05))

    # ================================================================
    # 融合
    # ================================================================
    if not signals:
        report.final_verdict = FinalVerdict.NO_EDGE
        report.summary = "有效信号不足"
        report.warnings = warnings
        return

    dir_scores = {"home": 0.0, "draw": 0.0, "away": 0.0}
    total_w = 0.0

    for direction, score, weight in signals:
        if direction in dir_scores:
            dir_scores[direction] += score * weight
            total_w += weight
        elif direction == "confirm" and con and con.market_direction.value != "unclear":
            dir_scores[con.market_direction.value] += score * weight
            total_w += weight
        elif direction == "against_favorite":
            if con and con.market_direction.value == "home":
                dir_scores["away"] += score * weight
            elif con and con.market_direction.value == "away":
                dir_scores["home"] += score * weight
            total_w += weight
        elif direction == "prior_home":
            dir_scores["home"] += score * weight
            total_w += weight
        elif direction == "prior_draw":
            dir_scores["draw"] += score * weight
            total_w += weight
        elif direction == "prior_away":
            dir_scores["away"] += score * weight
            total_w += weight

    if total_w == 0:
        report.final_verdict = FinalVerdict.NO_EDGE
        report.summary = "融合失败"
        report.warnings = warnings
        return

    # 归一化
    norm = {k: v / total_w for k, v in dir_scores.items()}

    # 先验平滑
    alpha = cfg.prior_alpha
    report.final_home_prob = alpha * cfg.prior_home + (1 - alpha) * norm["home"]
    report.final_draw_prob = alpha * cfg.prior_draw + (1 - alpha) * norm["draw"]
    report.final_away_prob = alpha * cfg.prior_away + (1 - alpha) * norm["away"]
    total = report.final_home_prob + report.final_draw_prob + report.final_away_prob
    report.final_home_prob /= total
    report.final_draw_prob /= total
    report.final_away_prob /= total

    # 推荐方向
    probs = {"home": report.final_home_prob, "draw": report.final_draw_prob, "away": report.final_away_prob}
    best_dir = max(probs, key=probs.get)
    best_p = probs[best_dir]
    second = sorted(probs.values(), reverse=True)[1]
    gap = best_p - second

    # ═══════════════════════════════════════════════════════
    # 反向赔率检查：主胜赔率太短 → 降级或找冷门价值
    # ═══════════════════════════════════════════════════════
    home_odds = report._market_home_odds if hasattr(report, '_market_home_odds') else None
    draw_odds = report._market_draw_odds if hasattr(report, '_market_draw_odds') else None
    away_odds = report._market_away_odds if hasattr(report, '_market_away_odds') else None

    if best_dir == "home" and home_odds and home_odds < 1.65:
        # 主胜赔率太短：需要更强的确认信号
        validator_confirmed = (val and val.verdict == ValidationVerdict.CONFIRMED)
        pricing_undervalues_home = (pri and pri.best_value_side == "home" and pri.best_ev > 0.03)

        if not (validator_confirmed and pricing_undervalues_home):
            # 寻找被低估的冷门方向
            underdog_candidates = []
            for side, odds in [("draw", draw_odds), ("away", away_odds)]:
                if odds and probs[side] > 0.18:
                    # 冷门方向概率 > 18% + 存在价值
                    if pri and pri.best_value_side == side:
                        underdog_candidates.append((side, probs[side], abs(pri.best_ev)))
                    elif probs[side] > 0.25:
                        underdog_candidates.append((side, probs[side], 0.0))

            if underdog_candidates:
                # 有人在赌博的世界里错了 — 选被低估的冷门
                underdog_candidates.sort(key=lambda x: x[2], reverse=True)
                best_dir = underdog_candidates[0][0]
                gap = 0.05  # 弱信号
                warnings.append(f"⚠️ 主胜赔率过短 ({home_odds})，转向冷门: {best_dir}")
            else:
                # 没有好的冷门选择 → 跳过
                best_dir = None
                gap = 0.0
                warnings.append(f"⚠️ 主胜赔率过短 ({home_odds}) 且无冷门替代，跳过")

    # 方向最终赋值
    report.recommended_direction = best_dir
    report.confidence_score = gap * (1.5 if best_dir != "home" else 1.0)
    report.cross_validation = xv

    if best_dir is None:
        report.final_verdict = FinalVerdict.NO_EDGE
    elif gap > cfg.high_confidence_gap and len(warnings) <= 1:
        report.final_verdict = FinalVerdict.HIGH_CONFIDENCE
    elif gap > cfg.moderate_confidence_gap:
        report.final_verdict = FinalVerdict.MODERATE_CONFIDENCE
    elif gap > cfg.low_confidence_gap:
        report.final_verdict = FinalVerdict.LOW_CONFIDENCE
    else:
        report.final_verdict = FinalVerdict.NO_EDGE

    dir_map = {"home": report.home_team, "draw": "平局", "away": report.away_team}
    report.summary = (
        f"{report.final_verdict.value} | "
        f"推荐: {dir_map.get(report.recommended_direction, '?')} | "
        f"home={report.final_home_prob:.1%} draw={report.final_draw_prob:.1%} away={report.final_away_prob:.1%}"
    )
    report.warnings = warnings


def generate_markdown_report(report: FinalReport) -> str:
    """生成 Markdown 可读报告"""
    lines = [
        f"# ⚽ 综合预测报告",
        f"",
        f"**{report.home_team} vs {report.away_team}**  {f'({report.league})' if report.league else ''}",
        f"",
        "---",
        "",
        "## 五步分析流程",
        "",
    ]
    for sr in report.step_reports:
        c = f" [置信度: {sr.confidence:.0%}]" if sr.confidence > 0 else ""
        lines.append(f"### Step {sr.step}: {sr.name}")
        lines.append(f"> {sr.conclusion}{c}")
        lines.append("")

    if report.cross_validation:
        lines.append("### 🔗 交叉验证")
        for cv in report.cross_validation:
            lines.append(f"- {cv}")
        lines.append("")

    lines.extend([
        "---",
        "",
        "## 🎯 最终判定",
        f"**裁决**: `{report.final_verdict.value}`",
    ])
    if report.recommended_direction:
        d = {"home": report.home_team, "draw": "平局", "away": report.away_team}
        lines.append(f"**推荐方向**: {d[report.recommended_direction]}")
    lines.append(f"**置信度**: {report.confidence_score:.1%}")
    lines.append("")

    lines.extend([
        "| 结果 | 概率 |",
        "|------|------|",
        f"| {report.home_team} 胜 | {report.final_home_prob:.1%} |",
        f"| 平局 | {report.final_draw_prob:.1%} |",
        f"| {report.away_team} 胜 | {report.final_away_prob:.1%} |",
        "",
    ])

    if report.position_sizing and report.position_sizing.sizing_label != "skip":
        ps = report.position_sizing
        lines.extend([
            "### 💰 仓位建议",
            f"- Kelly 原始: {ps.kelly_fraction:.2%}",
            f"- 建议仓位: **{ps.recommended_fraction:.2%}** ({ps.sizing_label})",
            f"- {ps.notes[0] if ps.notes else ''}",
            "",
        ])

    if report.warnings:
        lines.append("### ⚠️ 风险提示")
        for w in report.warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append(f"> {report.summary}")
    return "\n".join(lines)


# ============================================================
# 向后兼容
# ============================================================

def generate_markdown_report_legacy(report: FinalReport) -> str:
    return generate_markdown_report(report)
