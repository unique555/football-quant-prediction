"""公共工具函数 — 滚球调整 & CLV 分析 & 比分解析"""

from datetime import datetime, timezone


def get_match_score(score_obj: dict) -> dict:
    """统一比分解析: 优先 regularTime(90分钟), 回退 fullTime"""
    if not score_obj or not isinstance(score_obj, dict):
        return {"home": None, "away": None, "ht_home": None, "ht_away": None}

    # 优先取 regularTime (不包含点球), 回退 fullTime
    ft = score_obj.get("regularTime") or score_obj.get("fullTime") or {}
    ht = score_obj.get("halfTime") or {}

    return {
        "home": ft.get("home"),
        "away": ft.get("away"),
        "ht_home": ht.get("home"),
        "ht_away": ht.get("away"),
    }


def get_final_result(score_obj: dict) -> str:
    """返回 'H'/'D'/'A', 如果有点球则基于 regularTime 判断"""
    if not score_obj:
        return "?"
    rt = score_obj.get("regularTime") or score_obj.get("fullTime") or {}
    h, a = rt.get("home"), rt.get("away")
    if h is None or a is None:
        return "?"
    if h > a:
        return "H"
    if h == a:
        return "D"
    return "A"


def adjust_inplay(pred: dict, home_goals: int, away_goals: int, match_date: str) -> dict:
    """滚球调整: 根据当前比分 + 比赛时间修正概率"""
    try:
        kickoff = datetime.fromisoformat(match_date.replace("Z", "+00:00"))
        elapsed = max(0, (datetime.now(timezone.utc) - kickoff).total_seconds() / 60)
    except ValueError:
        elapsed = 45
    remaining = max(1, 90 - elapsed)
    goal_diff = home_goals - away_goals

    if goal_diff == 0:
        return pred

    adj_factor = min(0.95, max(0.05, abs(goal_diff) * 0.08 * remaining / 45))
    new_pred = dict(pred)

    if goal_diff > 0:
        new_pred["p_home"] = round(pred["p_home"] + adj_factor * pred["p_draw"], 4)
        new_pred["p_draw"] = round(pred["p_draw"] * (1 - adj_factor), 4)
        new_pred["p_away"] = round(1 - new_pred["p_home"] - new_pred["p_draw"], 4)
        new_pred["prediction"] = "主胜"
    else:
        new_pred["p_away"] = round(pred["p_away"] + adj_factor * pred["p_draw"], 4)
        new_pred["p_draw"] = round(pred["p_draw"] * (1 - adj_factor), 4)
        new_pred["p_home"] = round(1 - new_pred["p_away"] - new_pred["p_draw"], 4)
        new_pred["prediction"] = "客胜"

    new_pred["confidence"] = round(
        max(new_pred["p_home"], new_pred["p_draw"], new_pred["p_away"]), 4
    )
    new_pred["inplay_adjusted"] = True
    return new_pred


def simple_clv(pred: dict, odds: dict) -> dict:
    """模型公平赔率 vs 市场赔率的偏差百分比"""
    fair = {
        "home": round(1 / pred["p_home"], 2) if pred["p_home"] > 0 else 99,
        "draw": round(1 / pred["p_draw"], 2) if pred["p_draw"] > 0 else 99,
        "away": round(1 / pred["p_away"], 2) if pred["p_away"] > 0 else 99,
    }
    clv = {}
    for side, o_key in [("home", "home"), ("draw", "draw"), ("away", "away")]:
        if odds.get(o_key, 0) > 1.01:
            clv[f"{side}_clv"] = round((fair[o_key] - odds[o_key]) / odds[o_key] * 100, 1)
    return clv
