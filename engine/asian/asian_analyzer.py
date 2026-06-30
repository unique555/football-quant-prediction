"""
亚盘水位分析器

解决优化点 #6: 缺少亚盘维度分析
亚盘市场深度远高于 1X2，升降盘/水位变化更能揭示机构真实态度
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class HandicapTrend(Enum):
    """亚盘走势"""
    UPGRADE = "upgrade"          # 升盘：机构加强信心
    DOWNGRADE = "downgrade"      # 降盘：信心减弱
    WATER_DROP = "water_drop"    # 盘口不变但水位下降
    WATER_RISE = "water_rise"    # 水位上升
    STABLE = "stable"            # 无变化


@dataclass
class AsianLine:
    """单条亚盘线"""
    handicap: float           # -1.5, -1.0, -0.75, -0.5, -0.25, 0, 0.25, ...
    home_water: float         # 上盘水位 (0.80 = 80水)
    away_water: float
    bookmaker: str


@dataclass
class AsianResult:
    """亚盘分析结果"""
    # 主流盘口 (成交量最大的线)
    main_handicap: Optional[float] = None
    main_home_water: float = 0.0
    main_away_water: float = 0.0

    # 初盘 → 即时盘变化
    trend: HandicapTrend = HandicapTrend.STABLE
    handicap_change: float = 0.0     # 盘口变动 (正=升盘)
    water_change: float = 0.0        # 水位变动 (正=主队水位升)

    # 机构分歧
    handicap_disagreement: float = 0.0  # 不同机构盘口标准差

    # 信号
    direction_signal: Optional[str] = None  # "home" | "away" | None
    signal_strength: float = 0.0
    notes: list[str] = field(default_factory=list)


def analyze_asian_handicap(
    current_lines: list[AsianLine],
    opening_lines: Optional[list[AsianLine]] = None,
) -> AsianResult:
    """
    亚盘分析

    核心逻辑:
    - 升盘 + 降水 = 强看好信号
    - 降盘 + 升水 = 强看空信号
    - 盘口不变但水位剧烈波动 = 关注
    """
    if not current_lines:
        return AsianResult()

    result = AsianResult()
    notes = []

    # ---- 1. 找主流盘口（最多机构的盘口就是主流）----
    handicap_counts: dict[float, int] = {}
    handicap_water_map: dict[float, list[tuple[float, float]]] = {}
    for line in current_lines:
        h = line.handicap
        handicap_counts[h] = handicap_counts.get(h, 0) + 1
        if h not in handicap_water_map:
            handicap_water_map[h] = []
        handicap_water_map[h].append((line.home_water, line.away_water))

    if handicap_counts:
        main_h = max(handicap_counts, key=handicap_counts.get)
        waters = handicap_water_map[main_h]
        avg_home_water = sum(w[0] for w in waters) / len(waters)
        avg_away_water = sum(w[1] for w in waters) / len(waters)

        result.main_handicap = main_h
        result.main_home_water = round(avg_home_water, 3)
        result.main_away_water = round(avg_away_water, 3)

    # ---- 2. 初盘→即时盘变化 ----
    if opening_lines and result.main_handicap is not None:
        opening_h = _find_matching_opening(opening_lines, result.main_handicap)
        if opening_h is not None:
            h_change = result.main_handicap - opening_h.handicap
            w_change = result.main_home_water - opening_h.home_water

            result.handicap_change = h_change
            result.water_change = round(w_change, 3)

            # 判断趋势
            if h_change >= 0.25:
                result.trend = HandicapTrend.UPGRADE
                notes.append(f"亚盘升盘 +{h_change:.2f}，机构加强信心")
            elif h_change <= -0.25:
                result.trend = HandicapTrend.DOWNGRADE
                notes.append(f"亚盘降盘 {h_change:.2f}，信心减弱")
            elif w_change < -0.03:
                result.trend = HandicapTrend.WATER_DROP
                notes.append(f"盘口不变，主队水位降 {w_change:.2f}")
            elif w_change > 0.03:
                result.trend = HandicapTrend.WATER_RISE
                notes.append(f"盘口不变，主队水位升 +{w_change:.2f}")
            else:
                result.trend = HandicapTrend.STABLE

    # ---- 3. 机构分歧度 ----
    if len(current_lines) >= 2:
        handicaps = [l.handicap for l in current_lines]
        import statistics
        result.handicap_disagreement = statistics.stdev(handicaps) if len(handicaps) >= 2 else 0

    # ---- 4. 方向信号 ----
    if result.trend == HandicapTrend.UPGRADE:
        result.direction_signal = "home"
        result.signal_strength = 0.6 + abs(result.handicap_change) * 0.3
    elif result.trend == HandicapTrend.DOWNGRADE:
        result.direction_signal = "away"
        result.signal_strength = 0.6 + abs(result.handicap_change) * 0.3
    elif result.trend == HandicapTrend.WATER_DROP:
        result.direction_signal = "home"
        result.signal_strength = 0.35
    elif result.trend == HandicapTrend.WATER_RISE:
        result.direction_signal = "away"
        result.signal_strength = 0.35
    else:
        result.signal_strength = 0.1

    result.signal_strength = min(result.signal_strength, 1.0)
    result.notes = notes

    return result


def _find_matching_opening(
    opening_lines: list[AsianLine],
    current_handicap: float,
) -> Optional[AsianLine]:
    """在初盘线中找到最匹配当前盘口的线"""
    best = None
    best_diff = float("inf")
    for line in opening_lines:
        diff = abs(line.handicap - current_handicap)
        if diff < best_diff:
            best_diff = diff
            best = line
    return best
