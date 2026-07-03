"""
英超 2024-25 赛季合成数据生成器

模拟 20 支真实球队、380 场比赛、多家博彩公司赔率
用于端到端验证五步决策管道

数据特征：
- 基于真实球队实力层级（不保证比分准确，但分布合理）
- 赔率符合真实市场分布
- 各机构赔率有合理方差
"""

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta

random.seed(42)  # 可复现

# ============================================================
# 20 支英超球队 (真实名称 + 估计实力)
# ============================================================
TEAMS = [
    # (名称, TSI, 进攻力, 防守力, 主场加成)
    ("Man City", 88, 92, 82, 1.12),
    ("Arsenal", 84, 85, 88, 1.10),
    ("Liverpool", 83, 88, 80, 1.13),
    ("Chelsea", 79, 80, 78, 1.08),
    ("Tottenham", 76, 82, 72, 1.09),
    ("Newcastle", 77, 78, 76, 1.11),
    ("Aston Villa", 76, 80, 74, 1.10),
    ("Man United", 75, 74, 76, 1.10),
    ("Brighton", 72, 74, 70, 1.07),
    ("West Ham", 70, 70, 68, 1.08),
    ("Fulham", 69, 68, 70, 1.08),
    ("Brentford", 68, 72, 66, 1.06),
    ("Crystal Palace", 67, 66, 68, 1.06),
    ("Bournemouth", 66, 68, 64, 1.05),
    ("Nottingham Forest", 65, 64, 66, 1.07),
    ("Wolves", 65, 66, 64, 1.05),
    ("Everton", 63, 60, 66, 1.08),
    ("Leicester", 62, 64, 60, 1.06),
    ("Ipswich", 60, 62, 58, 1.05),
    ("Southampton", 58, 60, 56, 1.04),
]

# 博彩公司名称
BOOKMAKERS = [
    "bet365",
    "pinnacle",
    "william_hill",
    "betfair",
    "betway",
    "1xbet",
    "unibet",
    "bwin",
    "sbobet",
    "marathon",
]


@dataclass
class SyntheticMatch:
    """合成比赛数据"""

    # 比赛信息
    match_id: int
    date: str
    home_team: str
    away_team: str
    league_round: int

    # 基本面
    tsi_home: float
    tsi_away: float
    home_form: float
    away_form: float

    # 实际结果
    home_goals: int
    away_goals: int

    # 赔率 (多家机构)
    odds: list[dict]  # [{"bookmaker": "bet365", "home": 1.85, "draw": 3.60, "away": 4.20}, ...]

    # 亚盘 (取平均)
    asian_handicap: float = 0.0

    # 分类
    match_type: str = "even_contest"
    is_derby: bool = False

    @property
    def actual_outcome(self) -> str:
        if self.home_goals > self.away_goals:
            return "home"
        elif self.home_goals < self.away_goals:
            return "away"
        return "draw"

    @property
    def avg_home_odds(self) -> float:
        return sum(o["home"] for o in self.odds) / len(self.odds)

    @property
    def avg_draw_odds(self) -> float:
        return sum(o["draw"] for o in self.odds) / len(self.odds)

    @property
    def avg_away_odds(self) -> float:
        return sum(o["away"] for o in self.odds) / len(self.odds)


def _tsi_for(name: str) -> tuple:
    for t in TEAMS:
        if t[0] == name:
            return t
    return (name, 65, 65, 65, 1.05)


def _simulate_goals(
    home_tsi: float,
    away_tsi: float,
    home_att: float,
    away_att: float,
    home_def: float,
    away_def: float,
    home_bonus: float,
) -> tuple[int, int]:
    """基于泊松分布模拟进球（调整为真实联赛水平 ~2.7球/场）"""
    # 基准进球期望（英超 ~1.4主队 / ~1.3客队）
    league_base_home = 1.55
    league_base_away = 1.15

    # 实力调整
    att_ratio_home = home_att / 70
    def_ratio_away = away_def / 70
    att_ratio_away = away_att / 70
    def_ratio_home = home_def / 70

    home_xg = max(0.2, league_base_home * att_ratio_home / def_ratio_away * home_bonus)
    away_xg = max(0.15, league_base_away * att_ratio_away / def_ratio_home)

    # 加入随机性
    home_xg *= random.gauss(1.0, 0.12)
    away_xg *= random.gauss(1.0, 0.12)

    home_goals = max(0, int(round(random.gauss(home_xg, max(0.5, math.sqrt(home_xg) * 0.7)))))
    away_goals = max(0, int(round(random.gauss(away_xg, max(0.4, math.sqrt(away_xg) * 0.7)))))

    return home_goals, away_goals


def _generate_odds(
    home_goals: int, away_goals: int, home_tsi: float, away_tsi: float, home_bonus: float
) -> list[dict]:
    """
    根据实力差距生成合理的赔率

    思路：用 TSI 差距 + 随机噪声 → 公平赔率 → 各机构加 margin
    """
    tsi_gap = home_tsi - away_tsi

    # 基础公平概率
    base_home = 0.38 + tsi_gap * 0.004 + 0.08  # 主场优势
    base_draw = 0.28
    base_away = 1.0 - base_home - base_draw

    # 结果微调
    if home_goals > away_goals:
        base_home += random.uniform(0.02, 0.08)
    elif home_goals < away_goals:
        base_away += random.uniform(0.02, 0.08)
    else:
        base_draw += random.uniform(0.02, 0.06)

    # 归一化
    total = base_home + base_draw + base_away
    fair_p_home = base_home / total
    fair_p_draw = base_draw / total

    odds_list = []
    for bm_name in BOOKMAKERS:
        # 每个机构在公平赔率上加噪声(模拟真实机构间的分歧)
        noise = random.gauss(0, 0.02)
        p_h = max(0.05, min(0.85, fair_p_home + noise))
        noise2 = random.gauss(0, 0.015)
        p_d = max(0.05, min(0.50, fair_p_draw + noise2))
        p_a = 1.0 - p_h - p_d

        if p_a < 0.05:
            p_a = 0.05
            total2 = p_h + p_d + p_a
            p_h /= total2
            p_d /= total2
            p_a /= total2

        # 赔率 = 1/概率 × margin
        margin = random.uniform(0.92, 0.96)  # 返还率

        odds_list.append(
            {
                "bookmaker": bm_name,
                "home": round(1.0 / (p_h * (1 / margin)), 2),
                "draw": round(1.0 / (p_d * (1 / margin)), 2),
                "away": round(1.0 / (p_a * (1 / margin)), 2),
            }
        )

    return odds_list


def _asian_from_odds(odds_list: list[dict]) -> float:
    """从 1X2 赔率推断亚盘"""
    avg_h = sum(o["home"] for o in odds_list) / len(odds_list)
    avg_a = sum(o["away"] for o in odds_list) / len(odds_list)

    ratio = avg_h / avg_a if avg_a else 1.0

    # 简化映射
    if ratio < 0.30:
        return 2.0
    elif ratio < 0.45:
        return 1.5
    elif ratio < 0.60:
        return 1.0
    elif ratio < 0.72:
        return 0.75
    elif ratio < 0.82:
        return 0.5
    elif ratio < 0.92:
        return 0.25
    elif ratio < 1.08:
        return 0.0
    elif ratio < 1.22:
        return -0.25
    elif ratio < 1.40:
        return -0.5
    elif ratio < 1.65:
        return -0.75
    elif ratio < 2.0:
        return -1.0
    elif ratio < 2.5:
        return -1.5
    else:
        return -2.0


def _form_score(team_name: str, round_num: int) -> float:
    """生成半合理的状态波动"""
    base = 0.50
    # 基于球队实力微调
    for t in TEAMS:
        if t[0] == team_name:
            base = t[1] / 180  # 0.32~0.49
            break

    # 加入正弦波动（模仿赛季中状态起伏）
    wave = math.sin(round_num * 0.3) * 0.12
    noise = random.gauss(0, 0.08)

    return max(0.1, min(0.9, base + wave + noise))


def generate_season() -> list[SyntheticMatch]:
    """生成完整 380 场英超赛季（双循环，确保每队主客各一场 vs 其他19队）"""
    matches = []
    team_names = [t[0] for t in TEAMS]
    match_id = 0

    # 标准双循环赛程：轮次 1-19 = 上半程, 轮次 20-38 = 下半程（主客场对调）
    base_date = datetime(2024, 8, 16)
    n = len(team_names)  # 20

    for half in range(2):
        # 使用 circle method 生成单循环赛程
        teams = team_names[:]
        for round_in_half in range(n - 1):  # 19 轮
            round_num = half * (n - 1) + round_in_half + 1
            match_date = base_date + timedelta(days=(round_num - 1) * 7)

            for i in range(n // 2):
                if half == 0:
                    home_name = teams[i]
                    away_name = teams[n - 1 - i]
                else:
                    # 下半程主客场对调
                    home_name = teams[n - 1 - i]
                    away_name = teams[i]

                match_id += 1
                home = _tsi_for(home_name)
                away = _tsi_for(away_name)

                tsi_h, tsi_a = home[1], away[1]
                home_form = _form_score(home_name, round_num)
                away_form = _form_score(away_name, round_num)

                hg, ag = _simulate_goals(tsi_h, tsi_a, home[2], away[2], home[3], away[3], home[4])
                odds = _generate_odds(hg, ag, tsi_h, tsi_a, home[4])
                handicap = _asian_from_odds(odds)

                derby_pairs = [
                    {"Arsenal", "Tottenham"},
                    {"Man United", "Man City"},
                    {"Liverpool", "Everton"},
                    {"Chelsea", "Arsenal"},
                ]
                is_derby = {home_name, away_name} in derby_pairs

                matches.append(
                    SyntheticMatch(
                        match_id=match_id,
                        date=match_date.strftime("%Y-%m-%d"),
                        home_team=home_name,
                        away_team=away_name,
                        league_round=round_num,
                        tsi_home=tsi_h,
                        tsi_away=tsi_a,
                        home_form=home_form,
                        away_form=away_form,
                        home_goals=hg,
                        away_goals=ag,
                        odds=odds,
                        asian_handicap=handicap,
                        is_derby=is_derby,
                    )
                )

            # Rotate for next round (circle method)
            teams = [teams[0]] + [teams[-1]] + teams[1:-1]

    return matches


if __name__ == "__main__":
    season = generate_season()
    print(f"Generated {len(season)} matches")
    # 统计
    home_wins = sum(1 for m in season if m.actual_outcome == "home")
    draws = sum(1 for m in season if m.actual_outcome == "draw")
    away_wins = sum(1 for m in season if m.actual_outcome == "away")
    print(f"Home: {home_wins} ({home_wins / len(season):.1%})")
    print(f"Draw: {draws} ({draws / len(season):.1%})")
    print(f"Away: {away_wins} ({away_wins / len(season):.1%})")
    print(f"Avg goals: {sum(m.home_goals + m.away_goals for m in season) / len(season):.2f}")
    print(f"\nSample match: {season[0]}")
