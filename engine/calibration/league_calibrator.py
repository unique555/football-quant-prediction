"""
联赛特异性校准器

解决优化点 #9: 不同联赛有不同 baseline
意甲平局率 ~28%、英超 ~25%、德甲 ~22%
"""

from dataclasses import dataclass, field

from engine.config.settings import engine_config


@dataclass
class CalibratedProbabilities:
    """联赛校准后的概率"""

    home_prob: float
    draw_prob: float
    away_prob: float
    calibration_method: str
    adjustment_factors: dict = field(default_factory=dict)


def calibrate_by_league(
    raw_home: float,
    raw_draw: float,
    raw_away: float,
    league_code: str = "default",
) -> CalibratedProbabilities:
    """
    使用联赛历史分布对原始概率做 Bayesian 收缩

    逻辑: 原始概率 × (1 - shrinkage) + 联赛先验 × shrinkage
    shrinkage 由 league_profile.volatility 决定:
      波动越大(越容易爆冷) → shrinkage 越大 → 更靠近联赛均值
    """
    profile = engine_config.get_league_profile(league_code)
    shrinkage = profile.volatility * 0.3  # 0.10~0.18

    adj_factors = {"shrinkage": shrinkage}

    calibrated_home = raw_home * (1 - shrinkage) + profile.home_advantage * shrinkage
    calibrated_draw = raw_draw * (1 - shrinkage) + profile.draw_rate * shrinkage
    calibrated_away = raw_away * (1 - shrinkage) + profile.away_advantage * shrinkage

    # 归一化
    total = calibrated_home + calibrated_draw + calibrated_away
    if total > 0:
        calibrated_home /= total
        calibrated_draw /= total
        calibrated_away /= total

    return CalibratedProbabilities(
        home_prob=round(calibrated_home, 4),
        draw_prob=round(calibrated_draw, 4),
        away_prob=round(calibrated_away, 4),
        calibration_method="bayesian_shrinkage",
        adjustment_factors=adj_factors,
    )


def get_league_priors(league_code: str) -> tuple[float, float, float]:
    """获取联赛先验概率"""
    profile = engine_config.get_league_profile(league_code)
    return (profile.home_advantage, profile.draw_rate, profile.away_advantage)


def get_league_volatility(league_code: str) -> float:
    """获取联赛波动性"""
    return engine_config.get_league_profile(league_code).volatility


def get_league_goal_rate(league_code: str) -> float:
    """获取联赛场均进球"""
    return engine_config.get_league_profile(league_code).avg_goals
