"""
数据质量评估模块

对一场足球比赛的可分析程度进行综合打分，输出各维度检查项、
总分 (0-100) 与 analyzable 标记 (total_score >= 60)。

评估维度覆盖：赔率覆盖 / 赔率快照 / 历史数据 / 球队统计 /
伤缺信息 / 战术数据 / 成交量 / CLV。其中成交量为 ❌（API-Football
不提供），CLV 为 ⏳（需赛后才能计算）。
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 维度权重（总和 = 100）
# ---------------------------------------------------------------------------
# 权重反映该维度对最终量化预测的影响程度。赔率与基本面占比最大，
# 成交量与 CLV 虽重要但 API-Football 不可得，故权重适中。
_WEIGHTS: dict[str, int] = {
    "赔率覆盖": 18,
    "赔率快照": 12,
    "历史数据": 15,
    "球队统计": 15,
    "伤缺信息": 10,
    "战术数据": 10,
    "成交量": 10,
    "CLV": 10,
}

# 状态到分数的映射（每个维度自身的 0-100 分）
_STATUS_SCORE: dict[str, int] = {
    "✅": 100,
    "⚠️": 60,
    "❌": 0,
    "⏳": 50,  # 待定，中性
}


def assess(
    fixture: dict[str, Any],
    fundamental_data: dict[str, Any] | None,
    odds_aggregates: dict[str, Any] | None,
    motivation_data: dict[str, Any] | None,
) -> dict[str, Any]:
    """
    评估单场比赛的数据质量。

    Args:
        fixture: API-Football fixture 原始 dict
        fundamental_data: fundamental_analyzer.analyze 的返回值
        odds_aggregates: dict，如
            {"1x2": MarketAggregate|None, "asian_handicap": ..., "over_under": ...}
        motivation_data: motivation_analyzer.analyze 的返回值

    Returns:
        {
            "checks": [
                {"dimension": "赔率覆盖", "status": "✅", "detail": "6家庄家", "score": 100},
                ...
            ],
            "total_score": int,    # 0-100
            "analyzable": bool,    # total_score >= 60 时 True
        }
    """
    fundamental_data = fundamental_data or {}
    odds_aggregates = odds_aggregates or {}
    motivation_data = motivation_data or {}

    checks: list[dict[str, Any]] = []
    checks.append(_check_odds_coverage(odds_aggregates))
    checks.append(_check_odds_snapshot(odds_aggregates))
    checks.append(_check_history_data(fundamental_data))
    checks.append(_check_team_stats(fundamental_data))
    checks.append(_check_injury_info(motivation_data))
    checks.append(_check_tactical_data(fundamental_data))
    checks.append(_check_volume())
    checks.append(_check_clv())

    # 加权平均
    total_weight = sum(_WEIGHTS.values())
    weighted_sum = 0
    for chk in checks:
        dim = chk["dimension"]
        weight = _WEIGHTS.get(dim, 0)
        weighted_sum += weight * chk["score"]
    total_score = int(round(weighted_sum / total_weight)) if total_weight else 0

    return {
        "checks": checks,
        "total_score": total_score,
        "analyzable": total_score >= 60,
    }


# ---------------------------------------------------------------------------
# 维度检查实现
# ---------------------------------------------------------------------------

def _check_odds_coverage(odds_aggregates: dict[str, Any]) -> dict[str, Any]:
    """赔率覆盖：1x2 庄家数 >=5=✅, 3-4=⚠️, <3=❌"""
    market = odds_aggregates.get("1x2")
    count = _bookmaker_count(market)

    if count >= 5:
        status, detail = "✅", f"{count}家庄家"
    elif count >= 3:
        status, detail = "⚠️", f"仅{count}家庄家"
    else:
        status, detail = "❌", f"仅{count}家庄家或无1x2赔率"

    return _build_check("赔率覆盖", status, detail)


def _check_odds_snapshot(odds_aggregates: dict[str, Any]) -> dict[str, Any]:
    """赔率快照：1x2+亚盘+大小球 齐全=✅，2个市场=⚠️，<=1=❌"""
    markets_present = 0
    market_names = []
    for key, label in (
        ("1x2", "1x2"),
        ("asian_handicap", "亚盘"),
        ("over_under", "大小球"),
    ):
        if odds_aggregates.get(key) is not None:
            markets_present += 1
            market_names.append(label)

    if markets_present >= 3:
        status, detail = "✅", f"{' + '.join(market_names)} 三市场齐全"
    elif markets_present == 2:
        status, detail = "⚠️", f"仅{markets_present}个市场（{' + '.join(market_names)}）"
    else:
        status, detail = "❌", f"仅{markets_present}个市场，赔率快照不足"

    return _build_check("赔率快照", status, detail)


def _check_history_data(fundamental_data: dict[str, Any]) -> dict[str, Any]:
    """历史数据：standings(home+away) + h2h 齐全=✅，部分=⚠️，无=❌"""
    standings = fundamental_data.get("standings", {}) or {}
    has_standings = bool(standings.get("home")) and bool(standings.get("away"))
    h2h = fundamental_data.get("h2h", []) or []
    has_h2h = len(h2h) > 0

    if has_standings and has_h2h:
        status, detail = "✅", f"积分榜(主客) + 交锋{len(h2h)}场"
    elif has_standings or has_h2h:
        parts = []
        parts.append("积分榜" if has_standings else "无积分榜")
        parts.append(f"交锋{len(h2h)}场" if has_h2h else "无交锋")
        status, detail = "⚠️", "部分缺失：" + " / ".join(parts)
    else:
        status, detail = "❌", "无积分榜与交锋数据"

    return _build_check("历史数据", status, detail)


def _check_team_stats(fundamental_data: dict[str, Any]) -> dict[str, Any]:
    """球队统计：home_record + away_record 均非空=✅，部分=⚠️，无=❌"""
    home_rec = fundamental_data.get("home_record", {}) or {}
    away_rec = fundamental_data.get("away_record", {}) or {}
    has_home = bool(home_rec)
    has_away = bool(away_rec)

    if has_home and has_away:
        status, detail = "✅", "主客队赛季统计齐全"
    elif has_home or has_away:
        side = "主队" if has_home else "客队"
        status, detail = "⚠️", f"仅{side}统计可得"
    else:
        status, detail = "❌", "主客队统计均缺失"

    return _build_check("球队统计", status, detail)


def _check_injury_info(motivation_data: dict[str, Any]) -> dict[str, Any]:
    """伤缺信息：script_factors 含伤病+停赛等实质因子=✅，部分=⚠️，无=❌"""
    factors = motivation_data.get("script_factors", []) or []
    # 排除默认占位因子
    real_factors = [
        f for f in factors
        if f.get("factor") and "无可用剧本因子" not in f.get("factor", "")
    ]

    # 判断覆盖的类型：伤病 / 停赛 / 赛程密度 / 客场旅程
    covered_types = set()
    for f in real_factors:
        name = f.get("factor", "")
        if "伤病" in name:
            covered_types.add("伤病")
        elif "停赛" in name:
            covered_types.add("停赛")
        elif "赛程密度" in name:
            covered_types.add("赛程密度")
        elif "客场旅程" in name:
            covered_types.add("客场旅程")

    if len(covered_types) >= 3:
        status, detail = "✅", f"覆盖{len(covered_types)}类剧本因子：{'+'.join(sorted(covered_types))}"
    elif len(covered_types) >= 1:
        status, detail = "⚠️", f"仅覆盖{len(covered_types)}类：{'+'.join(sorted(covered_types))}"
    else:
        status, detail = "❌", "无伤停/赛程等剧本因子"

    return _build_check("伤缺信息", status, detail)


def _check_tactical_data(fundamental_data: dict[str, Any]) -> dict[str, Any]:
    """战术数据：home/away_record 含 shots/possession 等战术字段=✅，有限=⚠️，无=❌"""
    home_rec = fundamental_data.get("home_record", {}) or {}
    away_rec = fundamental_data.get("away_record", {}) or {}

    home_tactical = _has_tactical_fields(home_rec)
    away_tactical = _has_tactical_fields(away_rec)

    if home_tactical and away_tactical:
        status, detail = "✅", "主客队均含射门/控球等战术统计"
    elif home_tactical or away_tactical:
        side = "主队" if home_tactical else "客队"
        status, detail = "⚠️", f"仅{side}含战术统计"
    elif home_rec or away_rec:
        status, detail = "⚠️", "仅有基础胜负统计，无战术细节"
    else:
        status, detail = "❌", "无球队统计"

    return _build_check("战术数据", status, detail)


def _check_volume() -> dict[str, Any]:
    """成交量：API-Football 不提供，永远 ❌"""
    return _build_check("成交量", "❌", "API-Football 不提供成交量数据")


def _check_clv() -> dict[str, Any]:
    """CLV (Closing Line Value)：需赛后才能计算，永远 ⏳"""
    return _build_check("CLV", "⏳", "需赛后收盘赔率方可计算")


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _bookmaker_count(market: Any) -> int:
    """安全获取 MarketAggregate 的 bookmaker_count，兼容 None / dict / 对象。"""
    if market is None:
        return 0
    # dataclass 对象
    count = getattr(market, "bookmaker_count", None)
    if count is not None:
        return int(count)
    # dict 兼容
    if isinstance(market, dict):
        return int(market.get("bookmaker_count", 0) or 0)
    return 0


def _has_tactical_fields(record: dict[str, Any]) -> bool:
    """判断球队统计是否包含战术字段（射门/控球/传球等）。"""
    tactical_keys = ("avg_shots", "avg_possession", "shots", "possession",
                     "passes", "corners", "fouls")
    return any(record.get(k) for k in tactical_keys)


def _build_check(dimension: str, status: str, detail: str) -> dict[str, Any]:
    """构造单条检查结果。"""
    return {
        "dimension": dimension,
        "status": status,
        "detail": detail,
        "score": _STATUS_SCORE.get(status, 0),
    }
