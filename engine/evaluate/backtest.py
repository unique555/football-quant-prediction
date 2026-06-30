"""
回测引擎 — 按联赛/时间范围评估模型
→ 待实现
"""


def run_backtest(
    model_name: str,
    league: str,
    start_date: str,
    end_date: str,
) -> dict:
    """
    回测

    Returns:
        {
            "total_matches": int,
            "accuracy": float,
            "precision": float,
            "recall": float,
            "f1_score": float,
            "roi": float,
            "sharpe_ratio": float,
            "max_drawdown": float,
        }
    """
    raise NotImplementedError
