"""
蒙特卡洛模拟器 — 10,000 次模拟 → 比分概率分布
→ 待实现
"""

import numpy as np


def simulate(
    lambda_home: float,
    lambda_away: float,
    n_simulations: int = 10_000,
) -> dict:
    """
    蒙特卡洛模拟

    Returns:
        {
            "home_win_prob": float,
            "draw_prob": float,
            "away_win_prob": float,
            "scorelines": [(scoreline, prob), ...],  # Top 5
            "expected_home_goals": float,
            "expected_away_goals": float,
        }
    """
    home_goals = np.random.poisson(lambda_home, n_simulations)
    away_goals = np.random.poisson(lambda_away, n_simulations)

    home_wins = np.sum(home_goals > away_goals)
    draws = np.sum(home_goals == away_goals)
    away_wins = np.sum(home_goals < away_goals)

    return {
        "home_win_prob": home_wins / n_simulations,
        "draw_prob": draws / n_simulations,
        "away_win_prob": away_wins / n_simulations,
        "expected_home_goals": float(np.mean(home_goals)),
        "expected_away_goals": float(np.mean(away_goals)),
    }
