"""
输入验证器 — 数据完整性和有效性检查

解决优化点: #13 数据完整性检查 + #15 输入验证
"""
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class ValidationWarning:
    field: str
    severity: str    # "error" | "warning" | "info"
    message: str


@dataclass
class InputValidationResult:
    valid: bool
    warnings: list[ValidationWarning] = field(default_factory=list)
    data_quality_score: float = 1.0     # 数据质量评分 0-1
    missing_critical: list[str] = field(default_factory=list)


def validate_classification_input(
    tsi_home: float,
    tsi_away: float,
    asian_handicap: Optional[float] = None,
    initial_odds: Optional[tuple[float, float, float]] = None,
) -> InputValidationResult:
    """验证 Step 1 输入"""
    warnings = []
    critical = []
    w = ValidationWarning

    # TSI 范围
    if not (0 <= tsi_home <= 100):
        warnings.append(w("tsi_home", "warning", f"TSI 超出 0-100 范围: {tsi_home}"))
    if not (0 <= tsi_away <= 100):
        warnings.append(w("tsi_away", "warning", f"TSI 超出 0-100 范围: {tsi_away}"))

    # 亚盘
    if asian_handicap is not None and (asian_handicap > 3.0 or asian_handicap < -3.0):
        warnings.append(w("asian_handicap", "error", f"亚盘超出合理范围: {asian_handicap}"))

    # 赔率
    if initial_odds:
        ho, do, ao = initial_odds
        for name, val in [("home_odds", ho), ("draw_odds", do), ("away_odds", ao)]:
            if val <= 1.0:
                warnings.append(w(name, "error", f"赔率 ≤ 1.0 不合理: {val}"))
            elif val > 50.0:
                warnings.append(w(name, "warning", f"赔率异常高: {val}"))

    quality = 1.0 - (0.15 * len([x for x in warnings if x.severity == "error"])
                     + 0.05 * len([x for x in warnings if x.severity == "warning"]))

    return InputValidationResult(
        valid=all(x.severity != "error" for x in warnings),
        warnings=warnings,
        data_quality_score=max(quality, 0.0),
        missing_critical=critical,
    )


def validate_consensus_input(
    bookmaker_count: int,
    odds_list: list[float],
) -> InputValidationResult:
    """验证 Step 2 输入 — 机构数量和数据质量"""
    warnings = []
    critical = []
    w = ValidationWarning

    if bookmaker_count < 3:
        critical.append("bookmaker_count")
        warnings.append(w("bookmaker_count", "error",
                          f"机构数不足 ({bookmaker_count} < 3)，分析不可靠"))
    elif bookmaker_count < 5:
        warnings.append(w("bookmaker_count", "warning",
                          f"机构数较少 ({bookmaker_count} < 5)"))

    # 赔率变异极端检测
    if len(odds_list) >= 2:
        import statistics
        try:
            cv = statistics.stdev(odds_list) / statistics.mean(odds_list)
            if cv > 0.30:
                warnings.append(w("odds", "warning", f"赔率变异系数异常高: {cv:.2%}"))
        except (statistics.StatisticsError, ZeroDivisionError):
            pass

    quality = 1.0 - (0.20 * len(critical) + 0.05 * len([x for x in warnings if x.severity == "warning"]))

    return InputValidationResult(
        valid=len(critical) == 0,
        warnings=warnings,
        data_quality_score=max(quality, 0.0),
        missing_critical=critical,
    )


def validate_probabilities(home_p: float, draw_p: float, away_p: float) -> bool:
    """验证概率和 ≈ 1"""
    total = home_p + draw_p + away_p
    return 0.95 <= total <= 1.05


def validate_odds_sanity(home_odds: float, draw_odds: float, away_odds: float) -> bool:
    """赔率合理性快速检查"""
    if any(o <= 1.0 for o in [home_odds, draw_odds, away_odds]):
        return False
    raw = 1/home_odds + 1/draw_odds + 1/away_odds
    return 0.85 <= raw <= 1.25  # 合理返还率范围
