"""
ML 推理 — 加载训练好的 Stacking 模型，输出 1x2 概率

供 auto_analyze 调用，替代硬编码的 tsi=50。
实现"市场为主 + 自研修正"逻辑：
  final_prob = market_prob + (ml_prob - market_prob) * trust_weight
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from services.feature_builder import FeatureBuilder
from services.ml.trainer import StackingTrainer

logger = logging.getLogger(__name__)

# 信任权重：控制自研模型的话语权
# 0.0 = 完全信市场，1.0 = 完全信模型
# 默认 0.3 = 模型有 30% 话语权，市场有 70%
DEFAULT_TRUST_WEIGHT = 0.3


class MLPredictor:
    """ML 推理器"""

    def __init__(self, model: StackingTrainer | None = None):
        self.model = model
        self.feature_builder = FeatureBuilder()
        self.trust_weight = DEFAULT_TRUST_WEIGHT

    def is_ready(self) -> bool:
        """模型是否已加载"""
        return self.model is not None

    def predict(
        self,
        fixture: dict[str, Any],
        fundamental: dict[str, Any],
        odds_aggregates: dict[str, Any],
    ) -> dict[str, float] | None:
        """
        预测 1x2 概率。

        Returns:
            {"home": float, "draw": float, "away": float} 或 None（模型未就绪）
        """
        if not self.model:
            return None

        try:
            features = self.feature_builder.build(fixture, fundamental, odds_aggregates)
            feature_vector = np.array([[features.get(name, 0.0) for name in self.model.feature_names]])
            probs = self.model.predict_proba(feature_vector)[0]

            return {
                "home": float(probs[0]),
                "draw": float(probs[1]),
                "away": float(probs[2]),
            }
        except Exception as e:
            logger.warning("ML predict failed: %s", e)
            return None

    def apply_correction(
        self,
        market_probs: dict[str, float],
        ml_probs: dict[str, float] | None,
        trust_weight: float | None = None,
    ) -> dict[str, float]:
        """
        市场为主 + ML 修正

        final_prob = market_prob + (ml_prob - market_prob) * trust_weight

        Args:
            market_probs: {"home": 0.42, "draw": 0.29, "away": 0.28}
            ml_probs: {"home": 0.52, "draw": 0.26, "away": 0.22} 或 None
            trust_weight: 0~1，None 用默认值

        Returns:
            修正后概率（归一化）
        """
        if ml_probs is None:
            return market_probs

        tw = trust_weight if trust_weight is not None else self.trust_weight

        # 修正
        corrected = {}
        for side in ["home", "draw", "away"]:
            mkt = market_probs.get(side, 0.33)
            ml = ml_probs.get(side, 0.33)
            corrected[side] = mkt + (ml - mkt) * tw

        # 归一化
        total = sum(corrected.values())
        if total > 0:
            for side in corrected:
                corrected[side] /= total

        return corrected

    def compute_edge(
        self,
        final_probs: dict[str, float],
        market_probs: dict[str, float],
    ) -> dict[str, float]:
        """
        计算 Edge = 修正后概率 - 市场隐含概率

        Returns:
            {"home": float, "draw": float, "away": float}
        """
        return {
            side: final_probs.get(side, 0) - market_probs.get(side, 0)
            for side in ["home", "draw", "away"]
        }


# ============================================================
# 单例
# ============================================================

_predictor: MLPredictor | None = None


def get_predictor() -> MLPredictor:
    """获取 ML 推理器单例（自动加载最新模型）"""
    global _predictor
    if _predictor is None:
        model = StackingTrainer.load("latest")
        _predictor = MLPredictor(model=model)
        if model:
            logger.info("ML predictor initialized with model: metrics=%s", model.metrics)
        else:
            logger.info("ML predictor initialized without model (will use market probs only)")
    return _predictor


def reload_predictor() -> MLPredictor:
    """重新加载模型（重训后调用）"""
    global _predictor
    _predictor = None
    return get_predictor()
