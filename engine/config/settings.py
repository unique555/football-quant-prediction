"""
全局量化配置 — 所有可调参数集中管理

解决优化点 #12: 所有阈值全部硬编码 → 配置化
"""

from dataclasses import dataclass, field


@dataclass
class ClassifierConfig:
    """Step 1: 比赛分类配置"""

    # TSI 差距阈值
    strong_favorite_tsi_gap: float = 15.0
    moderate_favorite_tsi_gap: float = 8.0
    even_contest_max_gap: float = 8.0

    # 亚盘阈值 (主队让球为负)
    deep_handicap: float = -1.5  # 深盘
    moderate_handicap: float = -0.75  # 中盘
    shallow_handicap: float = -0.25  # 浅盘/平手

    # 冷门检测
    upset_shallow_handicap: float = -0.5  # 强队不让到此即视为浅盘
    upset_tsi_threshold: float = 10.0
    odds_drifting_threshold: float = 0.03  # 赔率漂移幅度
    key_absence_alert: int = 2  # 关键伤缺 ≥ 此数触发预警

    # 价值陷阱
    trap_low_odds: float = 1.30  # 赔率低于此 + 深盘 + TSI不足 = 陷阱
    trap_tsi_gap_max: float = 8.0
    trap_handicap_threshold: float = -1.0

    # 德比
    derby_confidence_penalty: float = 0.10


@dataclass
class ConsensusConfig:
    """Step 2: 机构共识配置"""

    # 共识级别 CV 阈值
    strong_consensus_cv: float = 0.03
    moderate_consensus_cv: float = 0.07
    weak_consensus_cv: float = 0.12

    # 方向判定
    direction_gap: float = 0.05  # 最大概率-次大概率需达此差
    min_bookmaker_count: int = 5  # 最少机构数才开始分析

    # 赔率走势
    odds_shift_threshold: float = 0.03  # 单家赔率变动 > 此值视为趋势


@dataclass
class ValidatorConfig:
    """Step 3: 指数验证配置"""

    # 支持度阈值
    confirmed_score: float = 0.30
    neutral_min: float = 0.0
    contradict_min: float = -0.30

    # 凯利权重
    kelly_support_weight: float = 0.30
    kelly_against_weight: float = -0.10

    # 成交量
    overheat_threshold: float = 0.70  # 单边 > 此值 = 过热
    overheat_penalty: float = -0.30
    volume_support: float = 0.15

    # 稳定性
    stability_high: float = 0.85
    stability_low: float = 0.60
    stability_reward: float = 0.20
    stability_penalty: float = -0.20

    # 平局信号
    draw_signal_threshold: float = 0.50  # 平赔 < min_win + 此值 = 平局信号
    draw_signal_penalty: float = -0.15


@dataclass
class PricingConfig:
    """Step 4: 市场定价配置"""

    ev_value_threshold: float = 0.05  # EV > 此值 = 有价值
    ev_overpriced_threshold: float = -0.03
    high_odds_ceiling: float = 8.0  # 高于此赔率，EV 不可靠
    high_odds_ev_discount: float = 0.5  # 高赔率 EV 打折系数


@dataclass
class SynthesisConfig:
    """Step 5: 综合判断配置"""

    # 权重分配
    weight_consensus: float = 0.35
    weight_validation: float = 0.25
    weight_pricing: float = 0.25
    weight_classification: float = 0.15

    # 先验
    prior_alpha: float = 0.30  # 平滑先验权重
    prior_home: float = 0.33
    prior_draw: float = 0.34
    prior_away: float = 0.33

    # 判定阈值
    high_confidence_gap: float = 0.10
    moderate_confidence_gap: float = 0.05
    low_confidence_gap: float = 0.02

    # 信号衰减
    decay_hours_halflife: float = 24.0  # 信号半衰期（小时）
    pre_match_peak_hours: float = 1.0  # 赛前多少小时内信号峰值


@dataclass
class LeagueProfile:
    """联赛特异性配置 — 解决优化点 #9"""

    name: str
    home_advantage: float = 0.37  # 主胜历史占比
    draw_rate: float = 0.27  # 平局历史占比
    away_advantage: float = 0.36  # 客胜历史占比
    avg_goals: float = 2.65  # 场均进球
    btts_rate: float = 0.52  # 双方进球率
    over_25_rate: float = 0.51  # >2.5球率
    volatility: float = 0.50  # 冷门率 (0-1, 越高越容易爆冷)


# 主流联赛预设
LEAGUE_PROFILES: dict[str, LeagueProfile] = {
    "epl": LeagueProfile(
        name="英超",
        home_advantage=0.43,
        draw_rate=0.25,
        away_advantage=0.32,
        avg_goals=2.78,
        btts_rate=0.54,
        over_25_rate=0.53,
        volatility=0.45,
    ),
    "laliga": LeagueProfile(
        name="西甲",
        home_advantage=0.45,
        draw_rate=0.26,
        away_advantage=0.29,
        avg_goals=2.55,
        btts_rate=0.48,
        over_25_rate=0.48,
        volatility=0.40,
    ),
    "serie_a": LeagueProfile(
        name="意甲",
        home_advantage=0.41,
        draw_rate=0.28,
        away_advantage=0.31,
        avg_goals=2.52,
        btts_rate=0.50,
        over_25_rate=0.47,
        volatility=0.50,
    ),
    "bundesliga": LeagueProfile(
        name="德甲",
        home_advantage=0.44,
        draw_rate=0.23,
        away_advantage=0.33,
        avg_goals=3.05,
        btts_rate=0.57,
        over_25_rate=0.58,
        volatility=0.48,
    ),
    "ligue1": LeagueProfile(
        name="法甲",
        home_advantage=0.42,
        draw_rate=0.28,
        away_advantage=0.30,
        avg_goals=2.58,
        btts_rate=0.49,
        over_25_rate=0.49,
        volatility=0.47,
    ),
    "eredivisie": LeagueProfile(
        name="荷甲",
        home_advantage=0.44,
        draw_rate=0.23,
        away_advantage=0.33,
        avg_goals=3.20,
        btts_rate=0.60,
        over_25_rate=0.62,
        volatility=0.55,
    ),
}


@dataclass
class EngineConfig:
    """总配置"""

    classifier: ClassifierConfig = field(default_factory=ClassifierConfig)
    consensus: ConsensusConfig = field(default_factory=ConsensusConfig)
    validator: ValidatorConfig = field(default_factory=ValidatorConfig)
    pricing: PricingConfig = field(default_factory=PricingConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
    league_profiles: dict[str, LeagueProfile] = field(default_factory=lambda: LEAGUE_PROFILES)

    # 联赛级联覆盖
    def get_league_profile(self, league_code: str) -> LeagueProfile:
        return self.league_profiles.get(
            league_code,
            LeagueProfile(name=league_code.upper()),  # 默认中性
        )


# 全局单例
engine_config = EngineConfig()
