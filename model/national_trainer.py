"""
国家队预测模型 — Poisson 评分, 处理 neutral 场地
训练数据: martj42/international_results (49,493场, 1872-2026)
"""
import pandas as pd
import numpy as np
from math import exp, factorial
from collections import defaultdict
import json, os
from typing import Optional

DATA_PATH = "/workspace/football-quant-prediction/data/international_results.csv"
RATINGS_FILE = "/workspace/football-quant-prediction/model/team_ratings_national.json"


def poisson_pmf(lmbda: float, k: int) -> float:
    if k < 0 or lmbda <= 0:
        return 0.0
    return exp(-lmbda) * (lmbda ** k) / factorial(k)


class NationalTeamRatingModel:
    """国家队实力评分模型 — 处理中立场地"""

    def __init__(self):
        self.ratings = {}          # team → {off, def, gp, w, d, l, gf, ga, pts}
        self.home_advantage = 1.20  # 非中立场地主队优势
        self.tournament_weight = {  # 赛事权重: 重要赛事更高
            "FIFA World Cup": 1.5,
            "UEFA Euro": 1.4,
            "Copa América": 1.4,
            "African Cup of Nations": 1.3,
            "AFC Asian Cup": 1.3,
            "CONCACAF Gold Cup": 1.2,
            "UEFA Nations League": 1.2,
        }
        self.load()

    # ---- 训练 ----

    def train(self, start_year: int = 2018, end_year: int = 2026):
        """训练模型 (从 martj42 CSV)"""
        df = pd.read_csv(DATA_PATH, low_memory=False)
        
        # 过滤年份
        df["year"] = pd.to_datetime(df["date"]).dt.year
        df = df[(df["year"] >= start_year) & (df["year"] <= end_year)]
        
        teams = defaultdict(lambda: {"gf": 0, "ga": 0, "gp": 0, "w": 0, "d": 0, "l": 0,
                                      "neutral_gp": 0, "home_gp": 0})
        
        for _, row in df.iterrows():
            home = str(row.get("home_team", ""))
            away = str(row.get("away_team", ""))
            try:
                hg = int(float(row.get("home_score", 0) or 0))
                ag = int(float(row.get("away_score", 0) or 0))
            except (ValueError, TypeError):
                continue
            neutral = str(row.get("neutral", "")).upper() == "TRUE"
            tournament = str(row.get("tournament", ""))
            
            weight = self.tournament_weight.get(tournament, 1.0)
            
            for team in [home, away]:
                if team not in teams:
                    teams[team] = {"gf": 0, "ga": 0, "gp": 0, "w": 0, "d": 0, "l": 0,
                                   "neutral_gp": 0, "home_gp": 0}
            
            teams[home]["gf"] += hg * weight
            teams[home]["ga"] += ag * weight
            teams[home]["gp"] += weight
            teams[away]["gf"] += ag * weight
            teams[away]["ga"] += hg * weight
            teams[away]["gp"] += weight
            
            if neutral:
                teams[home]["neutral_gp"] += weight
            else:
                teams[home]["home_gp"] += weight
            
            if hg > ag:
                teams[home]["w"] += weight
                teams[away]["l"] += weight
            elif hg == ag:
                teams[home]["d"] += weight
                teams[away]["d"] += weight
            else:
                teams[away]["w"] += weight
                teams[home]["l"] += weight

        # 全局平均进球
        all_gf = sum(s["gf"] for s in teams.values())
        all_gp = sum(s["gp"] for s in teams.values())
        global_avg = all_gf / all_gp if all_gp > 0 else 2.0

        # 计算攻防评分
        self.ratings = {}
        for name, s in teams.items():
            if s["gp"] < 3:
                continue
            self.ratings[name] = {
                "off": round((s["gf"] / s["gp"]) / global_avg, 3) if s["gp"] > 0 else 1.0,
                "def": round((s["ga"] / s["gp"]) / global_avg, 3) if s["gp"] > 0 else 1.0,
                "gp": round(s["gp"], 1), "w": round(s["w"], 1),
                "d": round(s["d"], 1), "l": round(s["l"], 1),
                "gf": round(s["gf"], 1), "ga": round(s["ga"], 1),
                "pts": round(s["w"] * 3 + s["d"], 1),
                "neutral_pct": round(s["neutral_gp"] / s["gp"], 2) if s["gp"] > 0 else 0.5,
            }

        print(f"   ✅ 训练完成: {len(self.ratings)} 支国家队 ({start_year}-{end_year})")
        self._save()
        return len(self.ratings)

    # ---- 预测 ----

    def predict(self, home_team: str, away_team: str, neutral: bool = False) -> dict:
        """泊松模型预测 (支持中立场地)"""
        default = {"off": 1.0, "def": 1.0}
        hr = self.ratings.get(home_team, default)
        ar = self.ratings.get(away_team, default)

        # 主场优势: 中立场地=1.0, 非中立=home_advantage
        ha = 1.0 if neutral else self.home_advantage
        home_xg = hr["off"] * ar["def"] * ha
        away_xg = ar["off"] * hr["def"] * (2 - ha) if ha > 1 else ar["off"] * hr["def"]

        # 限制极端值
        home_xg = max(0.2, min(home_xg, 4.5))
        away_xg = max(0.2, min(away_xg, 4.0))

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
            "neutral": neutral,
        }

    # ---- 批量回测 ----

    def backtest(self, year: int) -> dict:
        """对指定年份做回测"""
        df = pd.read_csv(DATA_PATH, low_memory=False)
        df["year"] = pd.to_datetime(df["date"]).dt.year
        df = df[df["year"] == year]
        
        correct = 0
        total = 0
        for _, row in df.iterrows():
            neutral = str(row.get("neutral", "")).upper() == "TRUE"
            pred = self.predict(
                str(row["home_team"]), str(row["away_team"]),
                neutral=neutral
            )
            hg = int(row["home_score"])
            ag = int(row["away_score"])
            actual = "主胜" if hg > ag else ("平局" if hg == ag else "客胜")
            if pred["prediction"] == actual:
                correct += 1
            total += 1
        
        acc = correct / total if total > 0 else 0
        return {"year": year, "matches": total, "accuracy": acc}

    # ---- 评分查询 ----

    def get_rating(self, team: str) -> Optional[dict]:
        return self.ratings.get(team)

    def has_team(self, team: str) -> bool:
        return team in self.ratings

    # ---- 持久化 ----

    def _save(self):
        with open(RATINGS_FILE, "w") as f:
            json.dump({
                "ratings": self.ratings,
                "home_advantage": self.home_advantage,
            }, f, indent=2, ensure_ascii=False)

    def load(self):
        if os.path.exists(RATINGS_FILE):
            with open(RATINGS_FILE) as f:
                data = json.load(f)
            self.ratings = data.get("ratings", {})
            self.home_advantage = data.get("home_advantage", 1.20)


# 单例
_national_model = None


def get_national_model() -> NationalTeamRatingModel:
    global _national_model
    if _national_model is None:
        _national_model = NationalTeamRatingModel()
    return _national_model
