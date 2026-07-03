"""
环境因子修正器 — 海拔、天气、休息天数、比赛阶段
→ 待实现
"""


def altitude_modifier(altitude_m: float) -> float:
    """海拔对xG的影响因子"""
    if altitude_m > 2200:
        return 1.12
    elif altitude_m > 1500:
        return 1.05
    return 1.0


def rest_modifier(days_rest: int) -> float:
    """休息天数对xG的影响因子"""
    if days_rest < 3:
        return 0.90
    return 1.0


def temperature_modifier(temp_c: float) -> float:
    """极端温度影响因子"""
    if temp_c > 32:
        return 0.94
    return 1.0


def knockout_modifier(is_knockout: bool) -> dict:
    """淘汰赛阶段修正"""
    if is_knockout:
        return {"xG_modifier": 0.92, "draw_bonus": 0.05}
    return {"xG_modifier": 1.0, "draw_bonus": 0.0}
