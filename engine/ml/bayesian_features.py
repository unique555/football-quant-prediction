"""
贝叶斯特征工程 — 358 维特征计算
→ 待实现
"""

import pandas as pd

FEATURE_GROUPS = {
    "basic": 26,  # 排名、ELO、积分
    "offensive": 48,  # xG、射门、射正、禁区触球
    "defensive": 48,  # xGA、被射门、抢断、拦截
    "h2h": 32,  # 往绩胜率、进球差
    "odds": 16,  # 凯利指数、赔率隐含概率
    "bayesian_rolling": 128,  # 贝叶斯滚动均值
    "form": 32,  # 近5场趋势
    "environmental": 18,  # 主客场、休息天数、旅程
    "squad": 10,  # 伤缺关键球员
}


def compute_features(match_data: dict) -> dict:
    """为单场比赛计算358维特征 → 待实现"""
    raise NotImplementedError


def compute_batch_features(matches_df) -> "pd.DataFrame":
    """批量特征计算 → 待实现"""
    raise NotImplementedError
