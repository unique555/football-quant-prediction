"""
评估指标
→ 待实现
"""

from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
)


def evaluate_predictions(y_true, y_pred, y_proba=None) -> dict:
    """计算全部评估指标 → 待实现"""
    metrics = {
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, average="weighted", zero_division=0),
        "recall": recall_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1_score": f1_score(y_true, y_pred, average="weighted", zero_division=0),
    }
    if y_proba is not None:
        metrics["brier_score"] = brier_score_loss(y_true, y_proba[:, 1])
        metrics["log_loss"] = log_loss(y_true, y_proba)
    return metrics
