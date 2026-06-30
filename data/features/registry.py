"""
特征注册表 — 特征元数据管理
→ 待实现
"""


# 特征元数据模板
FEATURE_SCHEMA = {
    "basic": {
        "description": "基础特征：排名、ELO、积分",
        "dim": 26,
        "refresh": "daily",
    },
    "offensive": {
        "description": "进攻特征：xG、射门、射正、禁区触球",
        "dim": 48,
        "refresh": "daily",
    },
    "defensive": {
        "description": "防守特征：xGA、被射门、抢断、拦截",
        "dim": 48,
        "refresh": "daily",
    },
    "h2h": {
        "description": "历史交锋特征",
        "dim": 32,
        "refresh": "per_match",
    },
    "odds": {
        "description": "赔率特征：凯利指数、隐含概率",
        "dim": 16,
        "refresh": "5min",
    },
    "bayesian_rolling": {
        "description": "贝叶斯滚动均值",
        "dim": 128,
        "refresh": "daily",
    },
    "form": {
        "description": "近期状态特征",
        "dim": 32,
        "refresh": "daily",
    },
    "environmental": {
        "description": "环境特征：主客场、休息、旅程",
        "dim": 18,
        "refresh": "per_match",
    },
    "squad": {
        "description": "阵容特征：伤缺、阵容变化",
        "dim": 10,
        "refresh": "per_match",
    },
}
