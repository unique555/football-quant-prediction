"""
Stacking 集成模型 — LightGBM + XGBoost + CatBoost
→ 待实现
"""
from sklearn.ensemble import StackingClassifier

# 模型注册表
MODEL_REGISTRY = {
    "1x2": None,         # 胜负平 StackingClassifier
    "over_15": None,     # >1.5球
    "over_25": None,     # >2.5球
    "over_35": None,     # >3.5球
    "btts": None,        # 双方进球
    "ht_1x2": None,      # 半场胜负
    "ht_over_05": None,  # 半场>0.5球
    "ht_over_15": None,  # 半场>1.5球
    "ht_btts": None,     # 半场BTTS
    "sh_over_15": None,  # 下半场>1.5球
    "home_cs": None,     # 主队零封
    "away_cs": None,     # 客队零封
}


def create_stacking_model() -> StackingClassifier:
    """创建 Stacking 集成模型 → 待实现"""
    raise NotImplementedError


def train_all_models(features_df, targets_dict, output_dir: str):
    """训练全部 13 个市场模型 → 待实现"""
    raise NotImplementedError


def load_model(market: str, version: str = "latest"):
    """加载已训练模型 → 待实现"""
    raise NotImplementedError
