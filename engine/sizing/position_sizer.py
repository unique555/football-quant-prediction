"""
仓位管理器 — Kelly 下注比例 + 风控

解决优化点 #8: 缺少投注仓位管理
量化系统核心: 方向 × 仓位 = 期望收益
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PositionSizingResult:
    """仓位建议"""
    # Kelly 原始
    kelly_fraction: float = 0.0           # 原始 Kelly 比例
    # 实际建议仓位 (加入风控层)
    recommended_fraction: float = 0.0      # 建议资金比例 (0-1)
    recommended_kelly_multiplier: float = 0.25  # 使用的 Kelly 倍数

    # 风险参数
    max_drawdown_limit: float = 0.10       # 最大回撤限制
    current_risk_budget: float = 1.0       # 当前风险预算

    # 分类
    sizing_label: str = "skip"             # "max" | "half" | "quarter" | "minimum" | "skip"
    notes: list[str] = field(default_factory=list)


def calculate_kelly(
    estimated_prob: float,
    odds: float,
    bankroll: float = 1.0,
    max_fraction: float = 0.10,            # 单笔最大 10%
    kelly_multiplier: float = 0.25,        # 1/4 Kelly 保守
    edge_threshold: float = 0.02,          # 至少 2% 优势才下注
) -> PositionSizingResult:
    """
    Kelly 仓位计算

    Kelly: f* = (p × odds - 1) / (odds - 1)
    实际: 1/4 Kelly + 单笔上限 + 优势下限

    Args:
        estimated_prob: 模型估计的真实概率
        odds: 可获得的最佳赔率
        bankroll: 总资金
        max_fraction: 单笔最大下注比例
        kelly_multiplier: Kelly 系数 (0.25 = 1/4 Kelly)
        edge_threshold: 最少边缘阈值
    """
    notes = []

    # 优势计算
    edge = estimated_prob * odds - 1

    if edge <= edge_threshold:
        return PositionSizingResult(
            kelly_fraction=0.0,
            sizing_label="skip",
            notes=[f"优势不足 ({edge:.2%} < {edge_threshold:.2%})"],
        )

    # Kelly 公式
    if odds <= 1.0:
        return PositionSizingResult(sizing_label="skip", notes=["赔率异常"])

    kelly_f = (estimated_prob * odds - 1) / (odds - 1)
    kelly_f = max(0, kelly_f)

    # 应用 Kelly 倍数
    adjusted = kelly_f * kelly_multiplier

    # 单笔上限
    adjusted = min(adjusted, max_fraction)

    # 取整到标签
    if adjusted >= max_fraction * 0.8:
        label = "max"
    elif adjusted >= 0.05:
        label = "half"
    elif adjusted >= 0.02:
        label = "quarter"
    else:
        label = "minimum"

    notes.append(f"EV={edge:.2%} | Kelly原始={kelly_f:.2%} | 建议={adjusted:.2%}")

    return PositionSizingResult(
        kelly_fraction=round(kelly_f, 4),
        recommended_fraction=round(adjusted, 4),
        recommended_kelly_multiplier=kelly_multiplier,
        sizing_label=label,
        notes=notes,
    )


# ============================================================
# 场景化 Kelly 调整
# ============================================================

def scene_adjusted_kelly(
    base_fraction: float,
    match_type: str,             # 来自 Step 1
    consensus_level: str,        # 来自 Step 2
    is_derby: bool = False,
) -> float:
    """
    根据比赛类型和共识级别调整 Kelly

    UPSET_RISK / VALUE_TRAP → 降低或归零
    STRONG consensus → 可适当加码
    """
    multiplier = 1.0

    # 按比赛类型调整
    type_adjustments = {
        "strong_favorite": 1.0,
        "moderate_favorite": 0.8,
        "even_contest": 0.6,
        "upset_risk": 0.3,          # 大幅降仓
        "derby_special": 0.4,
        "value_trap": 0.0,           # 直接归零
    }
    multiplier *= type_adjustments.get(match_type, 0.5)

    # 按共识级别调整
    consensus_adjustments = {
        "strong": 1.2,
        "moderate": 1.0,
        "weak": 0.7,
        "divergent": 0.3,
    }
    multiplier *= consensus_adjustments.get(consensus_level, 0.5)

    # 德比额外减
    if is_derby:
        multiplier *= 0.7

    return base_fraction * multiplier
