"""
概率校准器 — Platt Scaling / Isotonic Regression

将 ML 模型的原始概率输出校准为更准确的真实概率。
校准后的概率更接近实际发生率，对价值投注计算至关重要。
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class ProbabilityCalibrator:
    """概率校准器"""

    def __init__(self, method: str = "isotonic"):
        """
        Args:
            method: "isotonic" | "platt" | "temperature"
        """
        self.method = method
        self.calibrators: dict[str, Any] = {}  # 每个类别一个校准器

    def fit(self, probs: np.ndarray, labels: np.ndarray, n_classes: int = 3) -> "ProbabilityCalibrator":
        """
        拟合校准器。

        Args:
            probs: shape (n_samples, n_classes) — ML 模型原始概率
            labels: shape (n_samples,) — 真实标签 (0,1,2)
            n_classes: 类别数
        """
        from sklearn.isotonic import IsotonicRegression

        self.calibrators = {}
        for cls in range(n_classes):
            binary_labels = (labels == cls).astype(int)
            cls_probs = probs[:, cls]

            if self.method == "isotonic":
                cal = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99)
            elif self.method == "platt":
                from sklearn.linear_model import LogisticRegression
                cal = LogisticRegression(C=1.0, solver="lbfgs")
                # Platt 需要 2D 输入
                cal.fit(cls_probs.reshape(-1, 1), binary_labels)
            elif self.method == "temperature":
                # 温度缩放：简单参数化
                cal = _TemperatureScaler()
                cal.fit(cls_probs, binary_labels)
            else:
                raise ValueError(f"unknown method: {self.method}")

            if self.method == "isotonic":
                cal.fit(cls_probs, binary_labels)

            self.calibrators[cls] = cal

        logger.info("calibrator fitted: method=%s classes=%d samples=%d", self.method, n_classes, len(labels))
        return self

    def transform(self, probs: np.ndarray) -> np.ndarray:
        """
        校准概率。

        Args:
            probs: shape (n_samples, n_classes) 或 (n_classes,)

        Returns:
            校准后概率，归一化使每行和=1
        """
        single = probs.ndim == 1
        if single:
            probs = probs.reshape(1, -1)

        n_classes = probs.shape[1]
        calibrated = np.zeros_like(probs)

        for cls in range(n_classes):
            cal = self.calibrators.get(cls)
            if cal is None:
                calibrated[:, cls] = probs[:, cls]
                continue

            cls_probs = probs[:, cls]
            if self.method == "platt":
                calibrated[:, cls] = cal.predict_proba(cls_probs.reshape(-1, 1))[:, 1]
            else:
                calibrated[:, cls] = cal.transform(cls_probs) if hasattr(cal, "transform") else cal.predict(cls_probs)

        # 归一化
        row_sums = calibrated.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1, row_sums)
        calibrated = calibrated / row_sums

        return calibrated[0] if single else calibrated

    def save(self, path: str) -> None:
        """保存校准器"""
        import joblib
        joblib.dump({"method": self.method, "calibrators": self.calibrators}, path)
        logger.info("calibrator saved to %s", path)

    @classmethod
    def load(cls, path: str) -> "ProbabilityCalibrator":
        """加载校准器"""
        import joblib
        data = joblib.load(path)
        obj = cls(method=data["method"])
        obj.calibrators = data["calibrators"]
        return obj


class _TemperatureScaler:
    """温度缩放 — 单参数校准"""

    def __init__(self):
        self.temperature = 1.0

    def fit(self, probs: np.ndarray, labels: np.ndarray):
        from scipy.optimize import minimize

        def nll(T):
            scaled = self._scale(probs, T[0])
            loss = 0.0
            for i, label in enumerate(labels):
                p = max(scaled[i], 1e-7)
                loss -= np.log(p) if label == 1 else np.log(1 - p)
            return loss

        result = minimize(nll, x0=[1.0], method="Nelder-Mead")
        self.temperature = result.x[0]

    def transform(self, probs: np.ndarray) -> np.ndarray:
        return self._scale(probs, self.temperature)

    def predict(self, probs: np.ndarray) -> np.ndarray:
        return self.transform(probs)

    @staticmethod
    def _scale(probs: np.ndarray, T: float) -> np.ndarray:
        logits = np.log(np.clip(probs, 1e-7, 1 - 1e-7))
        scaled_logits = logits / max(T, 0.1)
        return 1 / (1 + np.exp(-scaled_logits))
