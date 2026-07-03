"""
ML 训练管线 — LightGBM + XGBoost + CatBoost Stacking

训练流程：
  1. 收集历史比赛数据（API-Football fixtures + odds）
  2. 构建特征向量（feature_builder）
  3. 训练 3 个 base learner（LGB / XGB / CatBoost）
  4. Stacking 元学习器（LogisticRegression）
  5. 概率校准（Isotonic Regression）
  6. 评估（Brier Score / Log Loss / Accuracy）
  7. 序列化保存 + MLflow 记录
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from services.feature_builder import FeatureBuilder
from services.ml.calibrator import ProbabilityCalibrator

logger = logging.getLogger(__name__)

MODELS_DIR = os.environ.get("MODELS_DIR", "/app/models_store")
LABELS = ["home_win", "draw", "away_win"]


class StackingTrainer:
    """Stacking 集成模型训练器"""

    def __init__(self):
        self.base_models: dict[str, Any] = {}
        self.meta_model: Any = None
        self.calibrator: ProbabilityCalibrator | None = None
        self.feature_names: list[str] = []
        self.metrics: dict[str, float] = {}

    def train(
        self,
        features_df: pd.DataFrame,
        labels: np.ndarray,
        feature_names: list[str],
    ) -> dict[str, float]:
        """
        训练完整 Stacking 模型。

        Args:
            features_df: 特征 DataFrame (n_samples, n_features)
            labels: 标签数组 (n_samples,) — 0=主胜, 1=平, 2=客胜
            feature_names: 特征名列表
        """
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import StratifiedKFold

        import lightgbm as lgb
        import xgboost as xgb
        from catboost import CatBoostClassifier

        self.feature_names = feature_names
        X = features_df[feature_names].values
        y = labels

        logger.info("training stacking model: %d samples, %d features", len(X), len(feature_names))

        # ── Base Learners ──
        # LightGBM
        lgb_model = lgb.LGBMClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            num_leaves=31, subsample=0.8, colsample_bytree=0.8,
            objective="multiclass", num_class=3, random_state=42, verbose=-1,
        )
        # XGBoost
        xgb_model = xgb.XGBClassifier(
            n_estimators=300, max_depth=6, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            objective="multi:softprob", num_class=3, random_state=42, verbosity=0,
        )
        # CatBoost
        cat_model = CatBoostClassifier(
            iterations=300, depth=6, learning_rate=0.05,
            loss_function="MultiClass", random_seed=42, verbose=0,
        )

        # ── Stacking：用 5-fold 交叉验证生成元特征 ──
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        n_samples = len(X)
        meta_features = np.zeros((n_samples, 9))  # 3 models × 3 classes

        for fold, (train_idx, val_idx) in enumerate(skf.split(X, y)):
            logger.info("  fold %d/5: train=%d val=%d", fold + 1, len(train_idx), len(val_idx))
            X_tr, X_val = X[train_idx], X[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            # 训练每个 base learner
            lgb_model.fit(X_tr, y_tr)
            xgb_model.fit(X_tr, y_tr)
            cat_model.fit(X_tr, y_tr)

            # 在验证集上预测，生成元特征
            meta_features[val_idx, 0:3] = lgb_model.predict_proba(X_val)
            meta_features[val_idx, 3:6] = xgb_model.predict_proba(X_val)
            meta_features[val_idx, 6:9] = cat_model.predict_proba(X_val)

        # ── 在全量数据上重新训练 base learners ──
        logger.info("retraining base learners on full data")
        lgb_model.fit(X, y)
        xgb_model.fit(X, y)
        cat_model.fit(X, y)

        self.base_models = {"lgb": lgb_model, "xgb": xgb_model, "cat": cat_model}

        # ── 训练元学习器 ──
        logger.info("training meta-learner (LogisticRegression)")
        self.meta_model = LogisticRegression(C=1.0, max_iter=500, multi_class="multinomial")
        self.meta_model.fit(meta_features, y)

        # ── 评估 ──
        from sklearn.metrics import accuracy_score, brier_score_loss, log_loss

        # 交叉验证预测
        cv_probs = self._predict_stacking(meta_features)
        cv_preds = np.argmax(cv_probs, axis=1)

        self.metrics = {
            "accuracy": float(accuracy_score(y, cv_preds)),
            "log_loss": float(log_loss(y, cv_probs, labels=[0, 1, 2])),
            "brier_score_home": float(brier_score_loss((y == 0).astype(int), cv_probs[:, 0])),
            "brier_score_draw": float(brier_score_loss((y == 1).astype(int), cv_probs[:, 1])),
            "brier_score_away": float(brier_score_loss((y == 2).astype(int), cv_probs[:, 2])),
        }

        logger.info("metrics: %s", self.metrics)

        # ── 概率校准 ──
        logger.info("fitting calibrator (isotonic)")
        self.calibrator = ProbabilityCalibrator(method="isotonic")
        self.calibrator.fit(cv_probs, y, n_classes=3)

        return self.metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """预测概率（校准后）"""
        # 生成元特征
        meta_features = np.zeros((len(X), 9))
        meta_features[:, 0:3] = self.base_models["lgb"].predict_proba(X)
        meta_features[:, 3:6] = self.base_models["xgb"].predict_proba(X)
        meta_features[:, 6:9] = self.base_models["cat"].predict_proba(X)

        # 元学习器预测
        probs = self.meta_model.predict_proba(meta_features)

        # 校准
        if self.calibrator:
            probs = self.calibrator.transform(probs)

        return probs

    def _predict_stacking(self, meta_features: np.ndarray) -> np.ndarray:
        """用元学习器预测"""
        return self.meta_model.predict_proba(meta_features)

    def save(self, version_tag: str | None = None) -> str:
        """保存模型到 models_store/"""
        import joblib

        version_tag = version_tag or f"stacking-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        model_dir = Path(MODELS_DIR) / version_tag
        model_dir.mkdir(parents=True, exist_ok=True)

        # 保存各组件
        joblib.dump(self.base_models["lgb"], model_dir / "lgb.pkl")
        joblib.dump(self.base_models["xgb"], model_dir / "xgb.pkl")
        joblib.dump(self.base_models["cat"], model_dir / "cat.pkl")
        joblib.dump(self.meta_model, model_dir / "meta.pkl")
        self.calibrator.save(str(model_dir / "calibrator.pkl"))

        # 保存元数据
        meta = {
            "version_tag": version_tag,
            "feature_names": self.feature_names,
            "metrics": self.metrics,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "n_features": len(self.feature_names),
        }
        (model_dir / "metadata.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False))

        logger.info("model saved to %s", model_dir)
        return version_tag

    @classmethod
    def load(cls, version_tag: str = "latest") -> "StackingTrainer | None":
        """加载模型"""
        import joblib

        model_dir = Path(MODELS_DIR)
        if not model_dir.exists():
            return None

        if version_tag == "latest":
            versions = sorted([d for d in model_dir.iterdir() if d.is_dir()])
            if not versions:
                return None
            model_dir = versions[-1]
        else:
            model_dir = model_dir / version_tag

        if not model_dir.exists():
            return None

        try:
            obj = cls()
            obj.base_models = {
                "lgb": joblib.load(model_dir / "lgb.pkl"),
                "xgb": joblib.load(model_dir / "xgb.pkl"),
                "cat": joblib.load(model_dir / "cat.pkl"),
            }
            obj.meta_model = joblib.load(model_dir / "meta.pkl")
            obj.calibrator = ProbabilityCalibrator.load(str(model_dir / "calibrator.pkl"))

            meta = json.loads((model_dir / "metadata.json").read_text())
            obj.feature_names = meta["feature_names"]
            obj.metrics = meta.get("metrics", {})

            logger.info("model loaded from %s", model_dir)
            return obj
        except Exception as e:
            logger.warning("failed to load model from %s: %s", model_dir, e)
            return None

    def features_hash(self) -> str:
        """计算特征哈希（用于版本管理）"""
        return hashlib.md5("|".join(self.feature_names).encode()).hexdigest()[:16]
