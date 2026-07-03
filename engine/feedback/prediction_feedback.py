"""
预测反馈闭环 + 残差分析框架

解决优化点: #10 反馈闭环 + #18 残差分析
每场比赛赛后自动摄取结果，计算预测残差，按联赛/类型/共识分层分析偏差
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OutcomeDirection(Enum):
    """实际结果方向"""

    HOME = "home"
    DRAW = "draw"
    AWAY = "away"


@dataclass
class PredictionRecord:
    """单次预测记录"""

    timestamp: datetime
    match_id: str
    league: str
    match_type: str  # 来自 Step 1

    # 预测
    pred_home_prob: float
    pred_draw_prob: float
    pred_away_prob: float
    predicted_direction: str
    confidence_score: float

    # 各步骤
    consensus_level: str
    validation_verdict: str
    pricing_verdict: str

    # 实际结果 (赛后填充)
    actual_outcome: Optional[OutcomeDirection] = None
    was_correct: Optional[bool] = None
    brier_score: Optional[float] = None  # 单场 Brier score


@dataclass
class ResidualReport:
    """残差分析报告"""

    total_predictions: int = 0
    overall_accuracy: float = 0.0
    overall_brier: float = 0.0

    # 按联赛分层
    by_league: dict[str, dict] = field(default_factory=dict)

    # 按比赛类型分层
    by_match_type: dict[str, dict] = field(default_factory=dict)

    # 按共识级别分层
    by_consensus: dict[str, dict] = field(default_factory=dict)

    # 校准曲线数据 (概率 bin → 实际频率)
    calibration_curve: list[tuple[float, float, int]] = field(default_factory=list)
    # [(prob_bin_center, actual_frequency, sample_count), ...]

    # 偏差热力图
    bias_matrix: dict[str, float] = field(default_factory=dict)

    # 发现的问题
    findings: list[str] = field(default_factory=list)


def record_prediction(pred: PredictionRecord) -> None:
    """记录一次预测（待实现存储层）→ 写入数据库或本地文件"""
    pass


def record_outcome(match_id: str, actual: OutcomeDirection) -> Optional[PredictionRecord]:
    """
    赛后记录实际结果，更新预测记录

    Returns:
        更新后的 PredictionRecord
    """
    pass


def compute_brier_score(
    pred_home: float,
    pred_draw: float,
    pred_away: float,
    actual: OutcomeDirection,
) -> float:
    """
    Brier Score 计算

    BS = (1/N) Σ (pred_i - actual_i)²
    越小越好，0 = 完美预测
    """
    actual_vec = {"home": (1, 0, 0), "draw": (0, 1, 0), "away": (0, 0, 1)}
    a_h, a_d, a_w = actual_vec[actual.value]

    bs = ((pred_home - a_h) ** 2 + (pred_draw - a_d) ** 2 + (pred_away - a_w) ** 2) / 3

    return bs


def analyze_residuals(records: list[PredictionRecord]) -> ResidualReport:
    """
    残差分析：按联赛/类型/共识分层，发现系统偏差

    → 待实现（需要数据持久化层后对接）
    """
    report = ResidualReport()

    # 筛选有实际结果的记录
    settled = [r for r in records if r.actual_outcome is not None]
    if not settled:
        report.findings.append("无已结算记录，无法分析")
        return report

    report.total_predictions = len(settled)

    # 总体准确率
    correct = sum(1 for r in settled if r.was_correct)
    report.overall_accuracy = correct / len(settled)

    # 总体 Brier
    briers = [r.brier_score for r in settled if r.brier_score is not None]
    if briers:
        report.overall_brier = sum(briers) / len(briers)

    # 按联赛分层
    by_league: dict[str, list[PredictionRecord]] = {}
    for r in settled:
        by_league.setdefault(r.league, []).append(r)
    for league, recs in by_league.items():
        acc = sum(1 for r in recs if r.was_correct) / len(recs)
        report.by_league[league] = {"count": len(recs), "accuracy": acc}

    # 按比赛类型分层
    by_type: dict[str, list[PredictionRecord]] = {}
    for r in settled:
        by_type.setdefault(r.match_type, []).append(r)
    for mtype, recs in by_type.items():
        acc = sum(1 for r in recs if r.was_correct) / len(recs)
        report.by_match_type[mtype] = {"count": len(recs), "accuracy": acc}

    # 按共识分层
    by_cons: dict[str, list[PredictionRecord]] = {}
    for r in settled:
        by_cons.setdefault(r.consensus_level, []).append(r)
    for level, recs in by_cons.items():
        acc = sum(1 for r in recs if r.was_correct) / len(recs)
        report.by_consensus[level] = {"count": len(recs), "accuracy": acc}

    # 偏差发现
    for mtype, info in report.by_match_type.items():
        if info["accuracy"] < 0.30 and info["count"] >= 10:
            report.findings.append(f"⚠️ {mtype} 类型准确率异常低 ({info['accuracy']:.0%})")
        elif info["accuracy"] > 0.60 and info["count"] >= 10:
            report.findings.append(f"✅ {mtype} 类型表现优异 ({info['accuracy']:.0%})")

    # 共识层级验证
    levels_order = ["strong", "moderate", "weak", "divergent"]
    accs = [report.by_consensus.get(level, {}).get("accuracy", 0) for level in levels_order]
    # 检查是否有越级（高共识不如低共识准确）
    for i in range(len(accs) - 1):
        if accs[i] > 0 and accs[i + 1] > 0 and accs[i] < accs[i + 1]:
            report.findings.append(f"⚠️ 共识等级颠倒: {levels_order[i]} < {levels_order[i + 1]}")

    return report
