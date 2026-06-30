"""
特征存储 — 统一特征读写接口
→ 待实现
"""

import pandas as pd


def load_features(league_id: int, date_from: str = None, date_to: str = None) -> pd.DataFrame:
    """加载已计算的特征 → 待实现"""
    raise NotImplementedError


def save_features(features_df: pd.DataFrame, version: str):
    """保存特征快照 → 待实现"""
    raise NotImplementedError
