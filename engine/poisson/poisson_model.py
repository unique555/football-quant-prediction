"""
泊松 xG 模型 — Bivariate Poisson 进球期望
→ 待实现
"""
import numpy as np
from scipy import stats


def compute_lambda(
    team: dict,
    opponent: dict,
    is_home: bool,
    modifiers: dict | None = None,
) -> float:
    """计算球队的进球期望 λ"""
    raise NotImplementedError


def predict_scoreline_prob(
    lambda_home: float,
    lambda_away: float,
    max_goals: int = 10,
) -> np.ndarray:
    """计算比分概率矩阵"""
    home_goals = np.arange(max_goals)
    away_goals = np.arange(max_goals)

    p_home = stats.poisson.pmf(home_goals[:, None], lambda_home)
    p_away = stats.poisson.pmf(away_goals[None, :], lambda_away)

    return p_home * p_away
