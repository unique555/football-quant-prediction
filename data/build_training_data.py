"""
真实数据加载器 + ELO 计算 + 特征工程

数据源: engsoccerdata (1888-2024 所有英格兰联赛真实结果)
从真实历史比赛结果计算 ELO，生成符合真实分布的赔率，
构建 ML 训练特征矩阵。
"""

from collections import defaultdict
from typing import Optional

import numpy as np
import pandas as pd

# ============================================================
# 1. 加载 & 过滤真实数据
# ============================================================


def load_england_data() -> pd.DataFrame:
    """加载英格兰联赛历史数据，过滤最近 10 个英超赛季"""
    df = pd.read_csv("/tmp/engsoccerdata.csv")
    # 过滤英超 (tier=1) + 最近赛季
    df = df[df["tier"] == 1]
    df = df[df["Season"] >= 2014]  # 2014-15 ~ 2023-24
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    # 统一队名 (engsoccerdata 有历史队名)
    name_map = {
        "Manchester United": "Man United",
        "Manchester City": "Man City",
        "Wolverhampton Wanderers": "Wolves",
        "Newcastle United": "Newcastle",
        "Tottenham Hotspur": "Tottenham",
        "Leeds United": "Leeds",
        "Norwich City": "Norwich",
        "Brighton & Hove Albion": "Brighton",
        "West Bromwich Albion": "West Brom",
        "Sheffield United": "Sheffield Utd",
        "Huddersfield Town": "Huddersfield",
        "Cardiff City": "Cardiff",
        "Nottingham Forest": "Nott'm Forest",
    }
    for old, new in name_map.items():
        df.loc[df["home"] == old, "home"] = new
        df.loc[df["visitor"] == old, "visitor"] = new

    print(f"Loaded {len(df)} Premier League matches ({df['Season'].min()}-{df['Season'].max()})")
    return df


# ============================================================
# 2. ELO 评分系统
# ============================================================


class ELOSystem:
    """基于真实比赛结果计算 ELO"""

    def __init__(self, k_base: float = 24, home_advantage: float = 100):
        self.k_base = k_base
        self.home_advantage = home_advantage
        self.ratings: dict[str, float] = defaultdict(lambda: 1500.0)
        self.history: dict[str, list[float]] = defaultdict(list)

    def expected_score(self, home: str, away: str) -> float:
        """ELO 期望得分 (主队)"""
        rating_h = self.ratings[home] + self.home_advantage
        rating_a = self.ratings[away]
        return 1.0 / (1.0 + 10 ** ((rating_a - rating_h) / 400.0))

    def update(
        self, home: str, away: str, home_goals: int, away_goals: int, k: Optional[float] = None
    ):
        """根据比赛结果更新 ELO"""
        expected = self.expected_score(home, away)
        # 实际得分
        if home_goals > away_goals:
            actual = 1.0
        elif home_goals < away_goals:
            actual = 0.0
        else:
            actual = 0.5

        # 进球差调整 K 值
        goal_diff = abs(home_goals - away_goals)
        if goal_diff >= 3:
            k_mult = 1.5
        elif goal_diff == 2:
            k_mult = 1.25
        else:
            k_mult = 1.0

        k_value = (k or self.k_base) * k_mult
        delta = k_value * (actual - expected)

        self.ratings[home] += delta
        self.ratings[away] -= delta
        self.history[home].append(self.ratings[home])
        self.history[away].append(self.ratings[away])

    def fit(self, df: pd.DataFrame):
        """按时间顺序计算所有球队的 ELO"""
        for _, row in df.iterrows():
            self.update(
                row["home"],
                row["visitor"],
                row["hgoal"],
                row["vgoal"],
            )
        print(f"ELO computed for {len(self.ratings)} teams")
        return self


# ============================================================
# 3. 赔率生成 (ELO → 赔率)
# ============================================================


def elo_to_odds(elo_home: float, elo_away: float) -> tuple[float, float, float]:
    """从 ELO 生成合理赔率 (10家机构，含合理噪声)"""
    elo_gap = elo_home - elo_away

    # ELO → 胜率
    p_home = 1.0 / (1.0 + 10 ** (-elo_gap / 400.0))
    # 平局率 (高ELO差 → 低平局)
    p_draw = max(0.08, 0.32 - abs(elo_gap) / 800.0)
    p_away = 1.0 - p_home - p_draw

    if p_away < 0.05:
        p_away = 0.05
        s = p_home + p_draw + p_away
        p_home /= s
        p_draw /= s

    # 公平赔率 + margin
    margin = np.random.uniform(0.93, 0.96)
    fair_h = 1.0 / p_home * (1 / margin)
    fair_d = 1.0 / p_draw * (1 / margin)
    fair_a = 1.0 / p_away * (1 / margin)

    # 加噪声模拟不同机构
    noise = np.random.normal(0, 0.02)
    return (
        round(max(1.05, fair_h + noise), 2),
        round(max(1.05, fair_d + noise * 0.5), 2),
        round(max(1.05, fair_a - noise * 0.7), 2),
    )


# ============================================================
# 4. 构建训练数据集
# ============================================================


def build_training_data(df: pd.DataFrame, elo: ELOSystem) -> pd.DataFrame:
    """为每场比赛构建特征向量"""
    features_list = []
    elo_snapshots: dict[str, float] = defaultdict(lambda: 1500.0)

    # 按时间顺序处理
    df = df.sort_values(["Season", "Date"]).reset_index(drop=True)

    # 近期战绩缓存
    team_recent: dict[str, list[int]] = defaultdict(list)  # 最近 5 场进球

    for idx, row in df.iterrows():
        home = row["home"]
        away = row["visitor"]
        hg, ag = row["hgoal"], row["vgoal"]

        # ELO 快照
        elo_h = elo_snapshots[home]
        elo_a = elo_snapshots[away]
        elo_gap = elo_h - elo_a

        # 近期战绩特征
        home_recent = team_recent.get(home, [])[-5:]
        away_recent = team_recent.get(away, [])[-5:]

        home_gf_last5 = np.mean([g[0] for g in home_recent]) if home_recent else 1.3
        home_ga_last5 = np.mean([g[1] for g in home_recent]) if home_recent else 1.2
        away_gf_last5 = np.mean([g[0] for g in away_recent]) if away_recent else 1.2
        away_ga_last5 = np.mean([g[1] for g in away_recent]) if away_recent else 1.3

        home_pts_last5 = (
            sum(3 if g[0] > g[1] else (1 if g[0] == g[1] else 0) for g in home_recent) / 5
            if home_recent
            else 1.5
        )
        away_pts_last5 = (
            sum(3 if g[0] > g[1] else (1 if g[0] == g[1] else 0) for g in away_recent) / 5
            if away_recent
            else 1.2
        )

        # 赔率 (从 ELO 生成)
        h_odds, d_odds, a_odds = elo_to_odds(elo_h, elo_a)

        # 特征向量
        features = {
            # 基础
            "match_id": idx,
            "season": row["Season"],
            "home": home,
            "away": away,
            "elo_home": elo_h,
            "elo_away": elo_a,
            "elo_gap": elo_gap,
            # 进攻 / 防守
            "home_gf_last5": home_gf_last5,
            "home_ga_last5": home_ga_last5,
            "away_gf_last5": away_gf_last5,
            "away_ga_last5": away_ga_last5,
            "home_pts_last5": home_pts_last5,
            "away_pts_last5": away_pts_last5,
            # 赔率特征
            "home_odds": h_odds,
            "draw_odds": d_odds,
            "away_odds": a_odds,
            "implied_home_prob": round(1.0 / h_odds, 4),
            "implied_draw_prob": round(1.0 / d_odds, 4),
            "implied_away_prob": round(1.0 / a_odds, 4),
            # 标签
            "home_goals": hg,
            "away_goals": ag,
            "outcome": "home" if hg > ag else ("draw" if hg == ag else "away"),
        }
        features_list.append(features)

        # 更新 ELO + 近期战绩
        exp = 1.0 / (1.0 + 10 ** ((elo_a - (elo_h + 100)) / 400.0))
        act = 1.0 if hg > ag else (0.5 if hg == ag else 0.0)
        k = 24 * (1.5 if abs(hg - ag) >= 3 else (1.25 if abs(hg - ag) == 2 else 1.0))
        elo_snapshots[home] += k * (act - exp)
        elo_snapshots[away] -= k * (act - exp)

        # 缓存近期
        team_recent[home] = (team_recent.get(home, []) + [(hg, ag)])[-5:]
        team_recent[away] = (team_recent.get(away, []) + [(ag, hg)])[-5:]

    result = pd.DataFrame(features_list)
    print(f"Built {len(result)} training samples with {len(result.columns)} features")
    return result


# ============================================================
# 5. 主流程
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("  ⚽ 真实数据 → 特征工程 → 训练集构建")
    print("=" * 60)
    print()

    # 加载
    df = load_england_data()

    # ELO
    elo = ELOSystem()
    elo.fit(df)

    # 构建训练集
    train_data = build_training_data(df, elo)

    # 保存
    train_data.to_csv("/workspace/football-quant-prediction/data/training_set.csv", index=False)
    print(f"\n✅ Training set saved: {len(train_data)} rows")
    print("   Outcome distribution:")
    print(train_data["outcome"].value_counts(normalize=True).to_string())
    print("\n   Top teams by ELO:")
    top = sorted(elo.ratings.items(), key=lambda x: x[1], reverse=True)[:8]
    for team, rating in top:
        print(f"     {team:<25s} {rating:.0f}")
