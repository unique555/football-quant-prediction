"""
回测服务
→ 待实现
"""


class BacktestService:
    """回测服务"""

    def run_backtest(self, model_name: str, league: str, start_date: str, end_date: str) -> str:
        """发起回测，返回 task_id"""
        raise NotImplementedError

    def get_backtest_status(self, task_id: str) -> dict:
        raise NotImplementedError

    def get_backtest_report(self, task_id: str) -> dict:
        raise NotImplementedError
