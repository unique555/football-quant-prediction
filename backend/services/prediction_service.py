"""
预测服务 — 核心业务逻辑
调用 engine/ 下的模型进行预测
→ 待实现
"""


class PredictionService:
    """预测服务聚合"""

    def predict_single(self, home_team: str, away_team: str) -> dict:
        """单场预测 → 待实现"""
        raise NotImplementedError

    def predict_batch(self, league: str) -> list[dict]:
        """批量预测 → 待实现"""
        raise NotImplementedError
