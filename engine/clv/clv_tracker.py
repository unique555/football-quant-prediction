"""
CLV (Closing Line Value) 追踪器

解决优化点 #5: 缺少临场水位变动检测
CLV 是体育预测学最稳定的 alpha 因子:
  初盘赔率 → 临场赔率的变动方向和幅度反映真实市场判断
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class OddsSnapshot:
    """单个时间点的赔率快照"""

    timestamp: datetime
    home_odds: float
    draw_odds: float
    away_odds: float


@dataclass
class CLVResult:
    """CLV 分析结果"""

    # 初盘 → 临场变化
    home_move_pct: float = 0.0  # 正=降水(受注), 负=升水(被抛)
    draw_move_pct: float = 0.0
    away_move_pct: float = 0.0

    # 综合判断
    clv_direction: Optional[str] = None  # "home" | "draw" | "away" | None
    clv_strength: float = 0.0  # 0-1, CLV 信号强度

    # 走势特征
    pattern: str = "unknown"  # "steaming" | "drifting" | "volatile" | "stable"
    max_drawdown: float = 0.0  # 赔率在过程中被拉升的最大幅度（抛压）

    # 亚洲盘专用
    handicap_move: Optional[float] = None  # 亚盘升降（正=升盘/降水，负=降盘/升水）
    handicap_move_pips: float = 0.0  # 亚盘变动幅度（多少档）

    notes: list[str] = field(default_factory=list)

    @property
    def is_informative(self) -> bool:
        """是否有有意义的 CLV 信号"""
        return self.clv_strength > 0.3


def analyze_clv(
    opening: OddsSnapshot,
    closing: OddsSnapshot,
    snapshots: Optional[list[OddsSnapshot]] = None,
    minutes_to_match: float = 0.0,
) -> CLVResult:
    """
    分析 CLV (初盘 → 临场)

    Args:
        opening: 初盘赔率（最早可获取）
        closing: 临场赔率（最接近开赛）
        snapshots: 中间时间序列快照（用于检测波动模式）
        minutes_to_match: 距离开赛剩余分钟数

    Returns:
        CLVResult
    """
    notes = []

    # ---- 1. 初盘→临场变化率 ----
    home_move = (opening.home_odds - closing.home_odds) / opening.home_odds
    draw_move = (opening.draw_odds - closing.draw_odds) / opening.draw_odds
    away_move = (opening.away_odds - closing.away_odds) / opening.away_odds

    # 正值 = 赔率下降 (受注), 负值 = 赔率上升 (被抛)

    # ---- 2. CLV 方向判断 ----
    moves = {"home": home_move, "draw": draw_move, "away": away_move}
    # 找最大降水方向（最受市场认可）
    best_side = max(moves, key=moves.get)
    best_move = moves[best_side]

    if best_move > 0.03:
        clv_direction = best_side
        clv_strength = min(best_move * 15, 1.0)  # 3%→0.45, 7%→1.0
    elif best_move > 0.01:
        clv_direction = best_side
        clv_strength = 0.2
    else:
        clv_direction = None
        clv_strength = 0.0

    # ---- 3. 走势模式检测 ----
    pattern = "unknown"
    max_drawdown = 0.0

    if snapshots and len(snapshots) >= 3:
        pattern, max_drawdown = _detect_pattern(snapshots, opening)

    if not snapshots:
        # 仅有头尾，判断整体走势
        if best_move > 0.05:
            pattern = "steaming"
            notes.append("赔率持续走低，市场信心增强")
        elif best_move < -0.05:
            pattern = "drifting"
            notes.append("赔率持续走高，市场信心减弱")
        else:
            pattern = "stable"

    # ---- 4. 亚盘联动分析 ----
    handicap_move = None
    handicap_move_pips = 0.0

    if snapshots:
        handicap_move = _estimate_handicap_move(closing, opening)

    return CLVResult(
        home_move_pct=round(home_move, 4),
        draw_move_pct=round(draw_move, 4),
        away_move_pct=round(away_move, 4),
        clv_direction=clv_direction,
        clv_strength=round(clv_strength, 4),
        pattern=pattern,
        max_drawdown=round(max_drawdown, 4),
        handicap_move=handicap_move,
        handicap_move_pips=handicap_move_pips,
        notes=notes,
    )


def _detect_pattern(
    snapshots: list[OddsSnapshot],
    opening: OddsSnapshot,
) -> tuple[str, float]:
    """从时间序列检测走势模式"""
    home_series = [s.home_odds for s in snapshots]

    # 最大回撤
    peak = opening.home_odds
    max_dd = 0.0
    for price in home_series:
        if price > peak:
            peak = price
        dd = (price - peak) / peak
        if dd < max_dd:
            max_dd = dd

    # 波动率判断模式
    if len(home_series) >= 2:
        changes = [
            abs(home_series[i] - home_series[i - 1]) / home_series[i - 1]
            for i in range(1, len(home_series))
        ]
        avg_change = sum(changes) / len(changes)

        if avg_change > 0.02:
            return "volatile", max_dd
        elif avg_change > 0.005:
            return "steaming" if home_series[-1] < opening.home_odds else "stable", max_dd
        else:
            return "stable", max_dd

    return "unknown", 0.0


def _estimate_handicap_move(
    closing: OddsSnapshot,
    opening: OddsSnapshot,
) -> Optional[str]:
    """从 1X2 赔率变动推断亚盘可能变动方向"""
    home_diff = closing.home_odds - opening.home_odds
    away_diff = closing.away_odds - opening.away_odds

    if home_diff < -0.10:
        return "home_up"  # 主队赔率大降 → 亚盘可能升盘
    elif away_diff < -0.10:
        return "away_up"
    elif home_diff > 0.10:
        return "home_down"
    elif away_diff > 0.10:
        return "away_down"
    return None
