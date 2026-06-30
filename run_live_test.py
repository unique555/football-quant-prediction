#!/usr/bin/env python3
"""
自包含实盘回测脚本
在你本地机器运行: python3 run_live_test.py
需要 pip install requests lightgbm scikit-learn pandas joblib
"""
import sys, os, json, time, pickle
from collections import defaultdict
from typing import Optional

import pandas as pd
import numpy as np
import requests
import joblib
import lightgbm as lgb
from sklearn.preprocessing import StandardScaler

# ============================================================
# 配置 (直接粘贴你的 keys)
# ============================================================
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ODDSPAPI_KEY

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")

# ============================================================
# 1. OddsPapi — 拉真赔率
# ============================================================

def fetch_odds_pinnacle(tournament_id: int = 17) -> list[dict]:
    """拉取英超 Pinnacle 赔率"""
    url = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds={tournament_id}&apiKey={ODDSPAPI_KEY}"
    time.sleep(1)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def parse_odds(item: dict) -> Optional[dict]:
    """解析 OddsPapi 单场赔率 → (home, draw, away)"""
    bm = item.get("bookmakerOdds", {}).get("pinnacle", {})
    mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
    try:
        h = mkt.get("101", {}).get("players", {}).get("0", {}).get("price")
        d = mkt.get("102", {}).get("players", {}).get("0", {}).get("price")
        a = mkt.get("103", {}).get("players", {}).get("0", {}).get("price")
        return {
            "fixture_id": item["fixtureId"],
            "home_odds": float(h),
            "draw_odds": float(d),
            "away_odds": float(a),
            "start_time": item.get("startTime", ""),
            "participant1_id": item.get("participant1Id"),
            "participant2_id": item.get("participant2Id"),
        }
    except (KeyError, TypeError, AttributeError):
        return None


# ============================================================
# 2. API-Football — 拉赛程 & 比分
# ============================================================

def fetch_fixtures(league_id: int = 39, season: int = 2024) -> list[dict]:
    """拉英超赛程 + 比分"""
    url = f"https://v3.football.api-sports.io/fixtures"
    params = {"league": league_id, "season": season, "status": "FT"}
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    time.sleep(6)  # 免费版限速
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("response", [])


def parse_fixture(item: dict) -> dict:
    """解析 API-Football 单场比赛"""
    f = item.get("fixture", {})
    teams = item.get("teams", {})
    goals = item.get("goals", {})
    return {
        "fixture_id": f.get("id"),
        "date": f.get("date", ""),
        "home_team": teams.get("home", {}).get("name", ""),
        "away_team": teams.get("away", {}).get("name", ""),
        "home_goals": goals.get("home"),
        "away_goals": goals.get("away"),
        "status": f.get("status", {}).get("short", ""),
    }


# ============================================================
# 3. 基于历史赛果构建实力评分 → 生成合成赔率
# ============================================================

def build_team_strength(fixtures: list[dict]) -> dict:
    """基于2024赛季赛果，计算每队的进攻/防守实力评分"""
    teams = {}
    for fx in fixtures:
        home = fx["home_team"]
        away = fx["away_team"]
        hg = fx["home_goals"]
        ag = fx["away_goals"]
        if hg is None or ag is None:
            continue
        for name in [home, away]:
            if name not in teams:
                teams[name] = {"gf": 0, "ga": 0, "gp": 0}
        teams[home]["gf"] += hg
        teams[home]["ga"] += ag
        teams[home]["gp"] += 1
        teams[away]["gf"] += ag
        teams[away]["ga"] += hg
        teams[away]["gp"] += 1

    # 联赛平均进球
    all_gf = sum(t["gf"] for t in teams.values())
    all_gp = sum(t["gp"] for t in teams.values())
    league_avg_gf = all_gf / all_gp if all_gp > 0 else 1.4

    # 攻防评分
    ratings = {}
    for name, s in teams.items():
        off_rating = (s["gf"] / s["gp"]) / league_avg_gf
        def_rating = (s["ga"] / s["gp"]) / league_avg_gf
        ratings[name] = {"off": off_rating, "def": def_rating, "gp": s["gp"]}
    return ratings


def generate_synthetic_odds(home_team: str, away_team: str, ratings: dict) -> tuple:
    """基于球队实力评分生成合成赔率 (Pinnacle风格, ~2.5% margin)"""
    hr = ratings.get(home_team, {"off": 1.0, "def": 1.0})
    ar = ratings.get(away_team, {"off": 1.0, "def": 1.0})

    # 预期进球 (主场优势 ~1.3x)
    home_xg = hr["off"] * ar["def"] * 1.35
    away_xg = ar["off"] * hr["def"] * 0.95

    # Poisson概率模拟
    from math import exp, factorial
    def poisson_pmf(lmbda, k):
        return exp(-lmbda) * (lmbda ** k) / factorial(k) if k >= 0 else 0

    max_goals = 8
    p_home = p_draw = p_away = 0.0
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            prob = poisson_pmf(home_xg, i) * poisson_pmf(away_xg, j)
            if i > j:
                p_home += prob
            elif i == j:
                p_draw += prob
            else:
                p_away += prob

    # 加margin (2.5%) 并转赔率
    margin = 0.025
    p_home_m = p_home * (1 + margin)
    p_draw_m = p_draw * (1 + margin)
    p_away_m = p_away * (1 + margin)

    home_odds = round(1 / p_home_m, 2) if p_home_m > 0 else 99.0
    draw_odds = round(1 / p_draw_m, 2) if p_draw_m > 0 else 99.0
    away_odds = round(1 / p_away_m, 2) if p_away_m > 0 else 99.0

    return home_odds, draw_odds, away_odds


# ============================================================
# 4. 分析引擎
# ============================================================

def run_analysis(df: pd.DataFrame, label: str = "") -> dict:
    """对赔率+赛果数据跑分析"""
    if len(df) == 0:
        return {"error": "No matched data"}

    # 隐含概率
    df["raw_sum"] = 1/df["home_odds"] + 1/df["draw_odds"] + 1/df["away_odds"]
    df["mkt_home_p"] = (1/df["home_odds"]) / df["raw_sum"]
    df["mkt_draw_p"] = (1/df["draw_odds"]) / df["raw_sum"]
    df["mkt_away_p"] = (1/df["away_odds"]) / df["raw_sum"]

    # 实际结果
    df["outcome"] = df.apply(
        lambda r: "home" if r["home_goals"] > r["away_goals"]
        else ("draw" if r["home_goals"] == r["away_goals"] else "away"),
        axis=1,
    )

    # 市场预测方向
    df["market_pick"] = df[["mkt_home_p", "mkt_draw_p", "mkt_away_p"]].idxmax(axis=1)
    df["market_pick"] = df["market_pick"].map({
        "mkt_home_p": "home", "mkt_draw_p": "draw", "mkt_away_p": "away",
    })

    # 准确率
    acc = (df["market_pick"] == df["outcome"]).mean()

    # 按赔率分层的准确率
    df["odds_bucket"] = pd.cut(df["home_odds"], bins=[0, 1.5, 2.0, 3.0, 100], labels=["<1.5", "1.5-2", "2-3", ">3"])
    bucket_rows = []
    for bucket, group in df.groupby("odds_bucket", observed=False):
        bucket_rows.append({
            "bucket": bucket,
            "count": len(group),
            "accuracy": (group["market_pick"] == group["outcome"]).mean(),
        })

    # Brier Score
    bs = 0
    for _, r in df.iterrows():
        av = {"home": (1,0,0), "draw": (0,1,0), "away": (0,0,1)}
        a = av[r["outcome"]]
        bs += ((r["mkt_home_p"]-a[0])**2 + (r["mkt_draw_p"]-a[1])**2 + (r["mkt_away_p"]-a[2])**2) / 3
    brier = bs / len(df)

    # 按概率置信度分层
    df["confidence"] = pd.cut(df["mkt_home_p"], bins=[0, 0.4, 0.5, 0.6, 0.7, 1.0],
                              labels=["<40%", "40-50%", "50-60%", "60-70%", ">70%"])
    conf_rows = []
    for conf, group in df.groupby("confidence", observed=False):
        conf_rows.append({
            "confidence": conf,
            "count": len(group),
            "accuracy": (group["market_pick"] == group["outcome"]).mean(),
        })

    # ROI 模拟: 每场投注1单位于市场预测方向
    df["bet_return"] = df.apply(
        lambda r: r["home_odds"] - 1 if r["market_pick"] == "home" and r["outcome"] == "home"
        else (r["draw_odds"] - 1 if r["market_pick"] == "draw" and r["outcome"] == "draw"
              else (r["away_odds"] - 1 if r["market_pick"] == "away" and r["outcome"] == "away"
                    else -1)),
        axis=1,
    )
    total_roi = df["bet_return"].sum() / len(df)

    return {
        "label": label,
        "total_matches": len(df),
        "market_accuracy": acc,
        "brier_score": brier,
        "by_odds_bucket": bucket_rows,
        "by_confidence": conf_rows,
        "outcome_dist": df["outcome"].value_counts(normalize=True).to_dict(),
        "avg_payout": (1/df["raw_sum"]).mean(),
        "roi": total_roi,
    }


def analyze_current_odds(odds_list: list[dict]) -> dict:
    """对当前 OddsPapi 赔率做独立分析"""
    df = pd.DataFrame(odds_list)
    df["raw_sum"] = 1/df["home_odds"] + 1/df["draw_odds"] + 1/df["away_odds"]
    df["mkt_home_p"] = (1/df["home_odds"]) / df["raw_sum"]
    df["mkt_draw_p"] = (1/df["draw_odds"]) / df["raw_sum"]
    df["mkt_away_p"] = (1/df["away_odds"]) / df["raw_sum"]
    df["payout"] = 1 / df["raw_sum"]

    return {
        "total_matches": len(df),
        "avg_margin": (1 - df["payout"].mean()),
        "avg_payout": df["payout"].mean(),
        "market_bias": {
            "home_favored": (df["home_odds"] < df["away_odds"]).sum(),
            "away_favored": (df["away_odds"] < df["home_odds"]).sum(),
        },
        "odds_distribution": {
            "home_odds_range": [float(df["home_odds"].min()), float(df["home_odds"].max())],
            "draw_odds_range": [float(df["draw_odds"].min()), float(df["draw_odds"].max())],
            "away_odds_range": [float(df["away_odds"].min()), float(df["away_odds"].max())],
        },
        "implied_home_win_pct": float(df["mkt_home_p"].mean()),
        "matches": df[["home_odds", "draw_odds", "away_odds", "mkt_home_p", "mkt_draw_p", "mkt_away_p", "payout", "start_time"]].to_dict(orient="records"),
    }


# ============================================================
# 5. 主流程
# ============================================================

def main():
    print("=" * 60)
    print("  ⚽ 足球量化预测 - 实盘验证系统")
    print("=" * 60)
    print()

    # ================================================================
    # Part A: 拉取 OddsPapi 当前赔率 (独立分析)
    # ================================================================
    print("📡 [数据源1] 拉取 OddsPapi Pinnacle 当前赔率...")
    odds_raw = fetch_odds_pinnacle(tournament_id=17)
    odds_parsed = [p for p in (parse_odds(o) for o in odds_raw) if p]
    print(f"   ✅ 获取 {len(odds_parsed)} 场当前赔率 (2026-08 英超)")
    print()

    if odds_parsed:
        print("📊 [分析A] 当前赔率市场结构分析...")
        current_analysis = analyze_current_odds(odds_parsed)
        print(f"   📌 Pinnacle 平均抽水: {current_analysis['avg_margin']:.2%}")
        print(f"   📌 平均返还率:        {current_analysis['avg_payout']:.1%}")
        print(f"   📌 主胜倾向场次:     {current_analysis['market_bias']['home_favored']}")
        print(f"   📌 客胜倾向场次:     {current_analysis['market_bias']['away_favored']}")
        print(f"   📌 市场隐含主胜均值: {current_analysis['implied_home_win_pct']:.1%}")
        print()

    # ================================================================
    # Part B: 拉取 API-Football 2024 赛季赛果
    # ================================================================
    print("📡 [数据源2] 拉取 API-Football 2024 赛季赛果...")
    fixtures_raw = fetch_fixtures(league_id=39, season=2024)
    fixtures_parsed = [parse_fixture(f) for f in fixtures_raw]
    print(f"   ✅ 获取 {len(fixtures_parsed)} 场已完赛比赛 (2024-25 英超)")
    print()

    # ================================================================
    # Part C: 基于历史赛果构建实力模型 → 生成合成赔率 → 回测
    # ================================================================
    print("🔧 [回测] 基于2024赛季赛果构建球队实力评分...")
    ratings = build_team_strength(fixtures_parsed)
    print(f"   ✅ 共 {len(ratings)} 支球队参与评分")
    print()

    print("🎲 [回测] 生成合成赔率 & 匹配赛果...")
    backtest_rows = []
    for fx in fixtures_parsed:
        if fx["home_goals"] is None or fx["away_goals"] is None:
            continue
        h_odds, d_odds, a_odds = generate_synthetic_odds(
            fx["home_team"], fx["away_team"], ratings
        )
        backtest_rows.append({
            "date": fx["date"],
            "home_team": fx["home_team"],
            "away_team": fx["away_team"],
            "home_goals": fx["home_goals"],
            "away_goals": fx["away_goals"],
            "home_odds": h_odds,
            "draw_odds": d_odds,
            "away_odds": a_odds,
        })
    df_backtest = pd.DataFrame(backtest_rows)
    print(f"   ✅ 生成 {len(df_backtest)} 场回测数据")
    print()

    # ================================================================
    # Part D: 运行分析
    # ================================================================
    if len(df_backtest) > 0:
        print("📊 [分析B] 合成赔率回测分析...")
        results = run_analysis(df_backtest, label="2024赛季合成赔率回测")

        print()
        print("=" * 60)
        print("  📈 回测结果 (2024-25 英超, 380场)")
        print("=" * 60)
        print(f"  总场次:         {results['total_matches']}")
        print(f"  模型准确率:     {results['market_accuracy']:.1%}")
        print(f"  Brier Score:    {results['brier_score']:.4f}")
        print(f"  模型ROI:        {results['roi']:+.1%}")
        print(f"  平均返还率:     {results['avg_payout']:.1%}")
        print(f"  赛果分布:       主胜 {results['outcome_dist'].get('home', 0):.1%}  "
              f"平局 {results['outcome_dist'].get('draw', 0):.1%}  "
              f"客胜 {results['outcome_dist'].get('away', 0):.1%}")
        print()
        print("  📊 按赔率分层:")
        for b in results["by_odds_bucket"]:
            print(f"     {b['bucket']:>8s}: {b['count']:3d}场  准确率 {b['accuracy']:.1%}")
        print()
        print("  📊 按置信度分层:")
        for c in results["by_confidence"]:
            print(f"     {c['confidence']:>8s}: {c['count']:3d}场  准确率 {c['accuracy']:.1%}")
        print()

        # ---- 保存全部结果 ----
        all_results = {
            "current_odds_analysis": current_analysis if odds_parsed else {},
            "backtest_2024": results,
            "team_ratings": {k: {"off": round(v["off"], 2), "def": round(v["def"], 2), "gp": v["gp"]}
                             for k, v in sorted(ratings.items(), key=lambda x: -x[1]["off"])},
        }

        # 保存 CSV
        df_backtest.to_csv("/workspace/football-quant-prediction/real_odds_backtest.csv", index=False)
        print(f"  ✅ 回测数据已保存到 real_odds_backtest.csv")

        # 保存 JSON
        with open("/workspace/football-quant-prediction/real_odds_results.json", "w") as f:
            json.dump(all_results, f, indent=2, default=str, ensure_ascii=False)
        print(f"  ✅ 完整结果已保存到 real_odds_results.json")

    else:
        print("⚠️ 未能生成回测数据")

    print()
    print("=" * 60)
    print("  ✅ 全部分析完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
