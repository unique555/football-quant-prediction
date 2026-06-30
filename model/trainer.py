"""
模型训练模块 — 基于历史数据构建球队实力评分 + Poisson 预测
"""
import pandas as pd
import numpy as np
from math import exp, factorial
from typing import Optional
from collections import defaultdict
import json, os, time

HISTORY_DB = "/workspace/football-quant-prediction/data/football_data_co_uk.csv"
RATINGS_FILE = "/workspace/football-quant-prediction/model/team_ratings.json"
MODEL_STATE = "/workspace/football-quant-prediction/model/model_state.json"


def poisson_pmf(lmbda: float, k: int) -> float:
    if k < 0 or lmbda <= 0:
        return 0.0
    return exp(-lmbda) * (lmbda ** k) / factorial(k)


class TeamRatingModel:
    """球队实力评分模型"""

    def __init__(self):
        self.ratings = {}          # team → {off, def, gp, w, d, l, pts, gf, ga}
        self.league_avgs = {}      # league → avg goals per game
        self.home_advantage = 1.35 # 主场优势系数
        self.last_trained = None
        self.load()

    # ---- 训练 ----

    def train(self, df: pd.DataFrame = None, seasons: list = None):
        """从历史数据训练球队评分"""
        if df is None:
            df = pd.read_csv(HISTORY_DB, low_memory=False)

        if seasons:
            df = df[df['season'].isin(seasons)]

        # 按时间排序确保只用历史数据
        if 'date' in df.columns:
            df = df.sort_values('date')

        ratings = defaultdict(lambda: {"gf": 0, "ga": 0, "gp": 0, "w": 0, "d": 0, "l": 0})
        league_stats = defaultdict(lambda: {"gf": 0, "gp": 0})

        for _, row in df.iterrows():
            home = str(row.get("home_team", ""))
            away = str(row.get("away_team", ""))
            hg = row.get("home_goals", 0) or 0
            ag = row.get("away_goals", 0) or 0
            league = row.get("league_name", "")

            for team in [home, away]:
                if team not in ratings:
                    ratings[team] = {"gf": 0, "ga": 0, "gp": 0, "w": 0, "d": 0, "l": 0}

            ratings[home]["gf"] += hg
            ratings[home]["ga"] += ag
            ratings[home]["gp"] += 1
            ratings[away]["gf"] += ag
            ratings[away]["ga"] += hg
            ratings[away]["gp"] += 1

            if hg > ag:
                ratings[home]["w"] += 1
                ratings[away]["l"] += 1
            elif hg == ag:
                ratings[home]["d"] += 1
                ratings[away]["d"] += 1
            else:
                ratings[away]["w"] += 1
                ratings[home]["l"] += 1

            league_stats[league]["gf"] += hg + ag
            league_stats[league]["gp"] += 1

        # 计算联赛平均进球
        for league, s in league_stats.items():
            self.league_avgs[league] = s["gf"] / s["gp"] if s["gp"] > 0 else 2.5

        # 全局平均
        all_gf = sum(s["gf"] for s in league_stats.values())
        all_gp = sum(s["gp"] for s in league_stats.values())
        global_avg = all_gf / all_gp if all_gp > 0 else 2.5

        # 计算攻防评分
        for name, s in ratings.items():
            if s["gp"] < 5:
                continue
            self.ratings[name] = {
                "off": round((s["gf"] / s["gp"]) / global_avg, 3),
                "def": round((s["ga"] / s["gp"]) / global_avg, 3),
                "gp": s["gp"], "w": s["w"], "d": s["d"], "l": s["l"],
                "pts": s["w"] * 3 + s["d"], "gf": s["gf"], "ga": s["ga"],
            }

        self.last_trained = pd.Timestamp.now().isoformat()
        self._save()
        return len(self.ratings)

    # ---- 预测 ----

    def predict(self, home_team: str, away_team: str, 
                league: str = "") -> dict:
        """泊松模型预测比赛"""
        default = {"off": 1.0, "def": 1.0}
        hr = self.ratings.get(home_team, default)
        ar = self.ratings.get(away_team, default)

        home_xg = hr["off"] * ar["def"] * self.home_advantage
        away_xg = ar["off"] * hr["def"] * (2 - self.home_advantage) if self.home_advantage > 1 else 0.95

        # 限制极端值
        home_xg = max(0.3, min(home_xg, 5.0))
        away_xg = max(0.2, min(away_xg, 4.5))

        p_home = p_draw = p_away = 0.0
        for i in range(9):
            for j in range(9):
                prob = poisson_pmf(home_xg, i) * poisson_pmf(away_xg, j)
                if i > j:
                    p_home += prob
                elif i == j:
                    p_draw += prob
                else:
                    p_away += prob

        # 最可能比分
        scores = {}
        for i in range(6):
            for j in range(6):
                scores[f"{i}-{j}"] = poisson_pmf(home_xg, i) * poisson_pmf(away_xg, j)
        top_scores = sorted(scores.items(), key=lambda x: -x[1])[:3]

        return {
            "home_xg": round(home_xg, 2),
            "away_xg": round(away_xg, 2),
            "p_home": round(p_home, 4),
            "p_draw": round(p_draw, 4),
            "p_away": round(p_away, 4),
            "prediction": max([("主胜", p_home), ("平局", p_draw), ("客胜", p_away)], key=lambda x: x[1])[0],
            "confidence": round(max(p_home, p_draw, p_away), 4),
            "top_scores": [(s, round(p, 4)) for s, p in top_scores],
        }

    # ---- 优化 ----

    def optimize_home_advantage(self, df: pd.DataFrame, season: int) -> float:
        """根据最新赛季自动调优主场优势系数"""
        season_df = df[df['season'] == season]
        if len(season_df) < 100:
            return self.home_advantage

        best_ha = self.home_advantage
        best_acc = 0

        for ha in [x / 100 for x in range(110, 155, 5)]:
            self.home_advantage = ha
            correct = 0
            total = 0
            for _, row in season_df.iterrows():
                pred = self.predict(
                    str(row.get("home_team", "")),
                    str(row.get("away_team", "")),
                )
                actual = "主胜" if row["home_goals"] > row["away_goals"] else (
                    "平局" if row["home_goals"] == row["away_goals"] else "客胜")
                if pred["prediction"] == actual:
                    correct += 1
                total += 1
                if total >= 200:
                    break
            acc = correct / total if total > 0 else 0
            if acc > best_acc:
                best_acc = acc
                best_ha = ha

        self.home_advantage = round(best_ha, 2)
        self._save()
        return self.home_advantage

    # ---- 持久化 ----

    def _save(self):
        data = {
            "ratings": self.ratings,
            "home_advantage": self.home_advantage,
            "league_avgs": self.league_avgs,
            "last_trained": self.last_trained,
        }
        with open(RATINGS_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def load(self):
        if os.path.exists(RATINGS_FILE):
            with open(RATINGS_FILE) as f:
                data = json.load(f)
            self.ratings = data.get("ratings", {})
            self.home_advantage = data.get("home_advantage", 1.35)
            self.league_avgs = data.get("league_avgs", {})
            self.last_trained = data.get("last_trained")

    def get_rating_display(self, team: str) -> str:
        r = self.ratings.get(team)
        if r:
            return f"攻{r['off']:.2f}/防{r['def']:.2f} | {r['w']}胜{r['d']}平{r['l']}负 | {r['pts']}分"
        return "无数据"


# 单例
_model = None


def get_model() -> TeamRatingModel:
    global _model
    if _model is None:
        _model = TeamRatingModel()
    return _model
