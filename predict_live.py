#!/usr/bin/env python3
"""
当下比赛预测 + MD 报告生成
用法: python3 predict_live.py
输出: /workspace/football-quant-prediction/live_prediction_report.md
"""

import os
import sys
import time
from math import exp, factorial
from typing import Optional

import pandas as pd
import requests

# ============================================================
# 配置
# ============================================================
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ODDSPAPI_KEY

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
REPORT_PATH = "/workspace/football-quant-prediction/live_prediction_report.md"

# ============================================================
# 1. 数据拉取
# ============================================================


def fetch_odds_pinnacle(tournament_id: int = 17) -> list[dict]:
    url = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds={tournament_id}&apiKey={ODDSPAPI_KEY}"
    time.sleep(1)
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_participants(sport_id: int = 10, tournament_id: int = 17) -> dict:
    url = f"https://api.oddspapi.io/v4/participants?sportId={sport_id}&tournamentId={tournament_id}&apiKey={ODDSPAPI_KEY}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_fixtures(league_id: int = 39, season: int = 2024) -> list[dict]:
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"league": league_id, "season": season, "status": "FT"}
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    time.sleep(6)
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("response", [])


# ============================================================
# 2. 解析
# ============================================================


def parse_odds(item: dict, participants: dict) -> Optional[dict]:
    bm = item.get("bookmakerOdds", {}).get("pinnacle", {})
    mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
    try:
        h = mkt.get("101", {}).get("players", {}).get("0", {}).get("price")
        d = mkt.get("102", {}).get("players", {}).get("0", {}).get("price")
        a = mkt.get("103", {}).get("players", {}).get("0", {}).get("price")
        p1_id = str(item.get("participant1Id", ""))
        p2_id = str(item.get("participant2Id", ""))
        return {
            "fixture_id": item["fixtureId"],
            "home_team": participants.get(p1_id, f"Team_{p1_id}"),
            "away_team": participants.get(p2_id, f"Team_{p2_id}"),
            "home_odds": float(h),
            "draw_odds": float(d),
            "away_odds": float(a),
            "start_time": item.get("startTime", ""),
        }
    except (KeyError, TypeError, AttributeError):
        return None


def parse_fixture(item: dict) -> dict:
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
# 3. 球队实力建模 (基于2024赛季赛果)
# ============================================================


def build_team_strength(fixtures: list[dict]) -> dict:
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
                teams[name] = {"gf": 0, "ga": 0, "gp": 0, "w": 0, "d": 0, "l": 0}
        teams[home]["gf"] += hg
        teams[home]["ga"] += ag
        teams[home]["gp"] += 1
        teams[away]["gf"] += ag
        teams[away]["ga"] += hg
        teams[away]["gp"] += 1
        if hg > ag:
            teams[home]["w"] += 1
            teams[away]["l"] += 1
        elif hg == ag:
            teams[home]["d"] += 1
            teams[away]["d"] += 1
        else:
            teams[away]["w"] += 1
            teams[home]["l"] += 1

    all_gf = sum(t["gf"] for t in teams.values())
    all_gp = sum(t["gp"] for t in teams.values())
    league_avg_gf = all_gf / all_gp if all_gp > 0 else 1.4

    ratings = {}
    for name, s in teams.items():
        off_rating = (s["gf"] / s["gp"]) / league_avg_gf
        def_rating = (s["ga"] / s["gp"]) / league_avg_gf
        pts = s["w"] * 3 + s["d"]
        ratings[name] = {
            "off": round(off_rating, 3),
            "def": round(def_rating, 3),
            "gp": s["gp"],
            "w": s["w"],
            "d": s["d"],
            "l": s["l"],
            "pts": pts,
            "gf": s["gf"],
            "ga": s["ga"],
        }
    return ratings


# ============================================================
# 4. 泊松模型预测
# ============================================================


def poisson_pmf(lmbda, k):
    if k < 0:
        return 0.0
    return exp(-lmbda) * (lmbda**k) / factorial(k)


def predict_match(home_team: str, away_team: str, ratings: dict) -> dict:
    """基于球队实力评分，用泊松模型预测比赛"""
    # 默认中等球队
    default = {"off": 1.0, "def": 1.0}
    hr = ratings.get(home_team, default)
    ar = ratings.get(away_team, default)

    # 预期进球 (主场优势 1.35x)
    home_xg = hr["off"] * ar["def"] * 1.35
    away_xg = ar["off"] * hr["def"] * 0.95

    # Poisson 概率计算
    max_goals = 8
    p_home = p_draw = p_away = 0.0
    score_probs = {}
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            prob = poisson_pmf(home_xg, i) * poisson_pmf(away_xg, j)
            score_probs[f"{i}-{j}"] = prob
            if i > j:
                p_home += prob
            elif i == j:
                p_draw += prob
            else:
                p_away += prob

    # 最可能比分
    top_scores = sorted(score_probs.items(), key=lambda x: -x[1])[:3]

    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "p_home": round(p_home, 4),
        "p_draw": round(p_draw, 4),
        "p_away": round(p_away, 4),
        "top_scores": [(s, round(p, 4)) for s, p in top_scores],
    }


def model_to_odds(p_home: float, p_draw: float, p_away: float, margin: float = 0.025) -> tuple:
    """概率转赔率 (含margin)"""
    p_home_m = p_home * (1 + margin)
    p_draw_m = p_draw * (1 + margin)
    p_away_m = p_away * (1 + margin)
    return (
        round(1 / p_home_m, 2) if p_home_m > 0 else 99.0,
        round(1 / p_draw_m, 2) if p_draw_m > 0 else 99.0,
        round(1 / p_away_m, 2) if p_away_m > 0 else 99.0,
    )


# ============================================================
# 5. 价值投注识别
# ============================================================


def find_value_bets(market_odds: dict, model_pred: dict) -> list:
    """对比市场赔率与模型预测，找价值投注"""
    outcomes = [
        ("主胜", "home_odds", "p_home"),
        ("平局", "draw_odds", "p_draw"),
        ("客胜", "away_odds", "p_away"),
    ]
    bets = []
    for label, odds_key, prob_key in outcomes:
        market_prob = 1 / market_odds[odds_key]  # 含margin的隐含概率
        model_prob = model_pred[prob_key]
        fair_odds = 1 / model_prob if model_prob > 0 else 999
        edge = (model_prob / market_prob - 1) if market_prob > 0 else 0
        bets.append(
            {
                "outcome": label,
                "market_odds": market_odds[odds_key],
                "model_prob": round(model_prob, 3),
                "market_implied_prob": round(market_prob, 3),
                "fair_odds": round(fair_odds, 2),
                "edge": round(edge, 3),
                "is_value": edge > 0.05,
            }
        )
    return bets


# ============================================================
# 6. 队名模糊匹配 (OddsPapi名 ↔ API-Football名)
# ============================================================


def fuzzy_match_team(op_name: str, ratings: dict) -> Optional[str]:
    """在ratings中查找最佳匹配的队名"""
    op_lower = op_name.lower().replace(" fc", "").replace(" afc", "")
    # 直接匹配
    for rname in ratings:
        r_lower = rname.lower().replace(" fc", "").replace(" afc", "")
        if op_lower == r_lower:
            return rname
        # 包含匹配
        if op_lower in r_lower or r_lower in op_lower:
            return rname
    # 模糊匹配: 关键词重叠
    best = None
    best_score = 0
    op_words = set(op_lower.split())
    for rname in ratings:
        r_words = set(rname.lower().split())
        score = len(op_words & r_words)
        if score > best_score:
            best_score = score
            best = rname
    return best if best_score >= 1 else None


# ============================================================
# 7. 生成 MD 报告
# ============================================================


def generate_report(
    current_matches: list,
    ratings: dict,
    backtest_results: dict,
    current_odds_analysis: dict,
) -> str:
    now_ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = []
    lines.append("# ⚽ 足球量化预测 - 实盘分析报告")
    lines.append("")
    lines.append(f"> 生成时间: {now_ts}  ")
    lines.append("> 数据源: OddsPapi (Pinnacle 赔率) + API-Football (赛果)  ")
    lines.append("> 模型: Poisson 分布 × 球队实力评分  ")
    lines.append("")

    # ---- Part 1: 当前市场概览 ----
    lines.append("## 一、当前赔率市场概览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|------|------|")
    lines.append(f"| 当前可交易场次 | {current_odds_analysis['total_matches']} |")
    lines.append(f"| Pinnacle 平均抽水 | {current_odds_analysis['avg_margin']:.2%} |")
    lines.append(f"| 平均返还率 | {current_odds_analysis['avg_payout']:.1%} |")
    lines.append(f"| 主胜倾向场次 | {current_odds_analysis['market_bias']['home_favored']} |")
    lines.append(f"| 客胜倾向场次 | {current_odds_analysis['market_bias']['away_favored']} |")
    lines.append(f"| 市场隐含主胜概率均值 | {current_odds_analysis['implied_home_win_pct']:.1%} |")
    lines.append("")

    # ---- Part 2: 当下比赛预测 ----
    lines.append("## 二、当下比赛预测 (vs 市场赔率)")
    lines.append("")
    lines.append(
        "每场比赛对比 **模型预测概率** 与 **Pinnacle 市场赔率隐含概率**，识别价值投注机会。"
    )
    lines.append("")

    for i, m in enumerate(current_matches, 1):
        home = m["home_team"]
        away = m["away_team"]
        pred = m["prediction"]
        value_bets = m["value_bets"]

        lines.append(f"### 比赛 {i}: {home} vs {away}")
        lines.append("")
        lines.append(f"**开赛时间**: {m['start_time'][:16].replace('T', ' ')}  ")
        lines.append(
            f"**模型评级**: 主队 {m.get('home_rating', 'N/A')} | 客队 {m.get('away_rating', 'N/A')}"
        )
        lines.append("")

        # 核心预测表
        lines.append("| 指标 | 主胜 | 平局 | 客胜 |")
        lines.append("|------|------|------|------|")
        lines.append(
            f"| **Pinnacle 赔率** | {m['home_odds']} | {m['draw_odds']} | {m['away_odds']} |"
        )
        lines.append(
            f"| **模型预测概率** | {pred['p_home']:.1%} | {pred['p_draw']:.1%} | {pred['p_away']:.1%} |"
        )
        # 市场隐含概率
        raw_sum = 1 / m["home_odds"] + 1 / m["draw_odds"] + 1 / m["away_odds"]
        mph = (1 / m["home_odds"]) / raw_sum
        mpd = (1 / m["draw_odds"]) / raw_sum
        mpa = (1 / m["away_odds"]) / raw_sum
        lines.append(f"| **市场隐含概率** | {mph:.1%} | {mpd:.1%} | {mpa:.1%} |")
        model_odds = model_to_odds(pred["p_home"], pred["p_draw"], pred["p_away"])
        lines.append(f"| **模型公平赔率** | {model_odds[0]} | {model_odds[1]} | {model_odds[2]} |")
        lines.append("")

        # 预测
        max_outcome = max(
            [("主胜", pred["p_home"]), ("平局", pred["p_draw"]), ("客胜", pred["p_away"])],
            key=lambda x: x[1],
        )
        lines.append(f"**🔮 模型预测**: **{max_outcome[0]}** (概率 {max_outcome[1]:.1%})")
        lines.append("")

        # xG
        lines.append(f"**预期进球**: 主 {pred['home_xg']} - {pred['away_xg']} 客  ")
        lines.append(
            "**最可能比分**: " + " | ".join([f"{s} ({p:.1%})" for s, p in pred["top_scores"]])
        )
        lines.append("")

        # 价值投注
        real_value = [vb for vb in value_bets if vb["is_value"]]
        if real_value:
            lines.append("**💎 价值投注机会:**")
            lines.append("")
            lines.append("| 投注方向 | 市场赔率 | 模型概率 | 公平赔率 | 期望优势 |")
            lines.append("|----------|----------|----------|----------|----------|")
            for vb in real_value:
                lines.append(
                    f"| **{vb['outcome']}** | {vb['market_odds']} | {vb['model_prob']:.1%} | {vb['fair_odds']} | **+{vb['edge']:.1%}** |"
                )
            lines.append("")
        else:
            lines.append("⚪ 无显著价值投注机会 (模型与市场一致)")
            lines.append("")

        # 详细对比
        lines.append("<details>")
        lines.append("<summary>📊 详细对比</summary>")
        lines.append("")
        lines.append("| 方向 | 市场赔率 | 市场概率 | 模型概率 | 公平赔率 | Edge |")
        lines.append("|------|----------|----------|----------|----------|------|")
        for vb in value_bets:
            flag = "⭐" if vb["is_value"] else ""
            lines.append(
                f"| {vb['outcome']} {flag} | {vb['market_odds']} | {vb['market_implied_prob']:.1%} | {vb['model_prob']:.1%} | {vb['fair_odds']} | {vb['edge']:+.1%} |"
            )
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # ---- Part 3: 球队实力评分 ----
    lines.append("## 三、球队实力评分 (基于2024-25英超赛季)")
    lines.append("")
    lines.append("评分逻辑: 以联赛平均进球为基准(1.0)，进攻/防守值 >1.0 表示优于平均。")
    lines.append("")
    lines.append("| 排名 | 球队 | 场次 | 胜/平/负 | 进球 | 失球 | 积分 | 进攻 | 防守 |")
    lines.append("|------|------|------|----------|------|------|------|------|------|")
    sorted_teams = sorted(ratings.items(), key=lambda x: -x[1]["pts"])
    for rank, (name, r) in enumerate(sorted_teams, 1):
        lines.append(
            f"| {rank} | {name} | {r['gp']} | {r['w']}/{r['d']}/{r['l']} | {r['gf']} | {r['ga']} | {r['pts']} | {r['off']:.2f} | {r['def']:.2f} |"
        )
    lines.append("")

    # ---- Part 4: 模型回测验证 ----
    if backtest_results and "error" not in backtest_results:
        bt = backtest_results
        lines.append(f"## 四、模型回测验证 (2024-25英超, {bt['total_matches']}场)")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 总场次 | {bt['total_matches']} |")
        lines.append(f"| 模型准确率 | {bt['market_accuracy']:.1%} |")
        lines.append(f"| Brier Score | {bt['brier_score']:.4f} |")
        lines.append(f"| 模拟ROI | {bt['roi']:+.1%} |")
        lines.append(f"| 平均返还率 | {bt['avg_payout']:.1%} |")
        lines.append(
            f"| 赛果分布 | 主 {bt['outcome_dist'].get('home', 0):.1%} / 平 {bt['outcome_dist'].get('draw', 0):.1%} / 客 {bt['outcome_dist'].get('away', 0):.1%} |"
        )
        lines.append("")

        lines.append("### 按赔率分层")
        lines.append("")
        lines.append("| 赔率区间 | 场次 | 准确率 |")
        lines.append("|----------|------|--------|")
        for b in bt.get("by_odds_bucket", []):
            lines.append(f"| {b['bucket']} | {b['count']} | {b['accuracy']:.1%} |")
        lines.append("")

        lines.append("### 按置信度分层")
        lines.append("")
        lines.append("| 置信度 | 场次 | 准确率 |")
        lines.append("|--------|------|--------|")
        for c in bt.get("by_confidence", []):
            lines.append(f"| {c['confidence']} | {c['count']} | {c['accuracy']:.1%} |")
        lines.append("")

    # ---- Part 5: 免责声明 ----
    lines.append("---")
    lines.append("")
    lines.append("## 免责声明")
    lines.append("")
    lines.append("> ⚠️ 本报告仅为量化模型实验输出，**不构成任何投注建议**。")
    lines.append("> 足球比赛结果受众多不可预测因素影响，过往表现不代表未来收益。")
    lines.append("> 模型使用 Poisson 分布 + 球队实力评分的简化方法，实际精度有限。")
    lines.append("> 请理性对待，风险自担。")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 8. 主流程
# ============================================================


def main():
    print("=" * 60)
    print("  ⚽ 当下比赛预测 - 生成 MD 报告")
    print("=" * 60)
    print()

    # Step 1: 拉取所有数据
    print("📡 拉取 OddsPapi 当前赔率...")
    odds_raw = fetch_odds_pinnacle(tournament_id=17)
    print(f"   ✅ 原始数据: {len(odds_raw)} 条")

    print("📡 拉取参赛队伍名称映射...")
    participants = fetch_participants(sport_id=10, tournament_id=17)
    print(f"   ✅ 队伍映射: {len(participants)} 个")

    print("📡 拉取 API-Football 2024赛季赛果...")
    fixtures_raw = fetch_fixtures(league_id=39, season=2024)
    fixtures_parsed = [parse_fixture(f) for f in fixtures_raw]
    print(f"   ✅ 赛果: {len(fixtures_parsed)} 场")
    print()

    # Step 2: 构建实力评分
    print("🔧 构建球队实力评分...")
    ratings = build_team_strength(fixtures_parsed)
    print(f"   ✅ {len(ratings)} 支球队")
    print()

    # Step 3: 解析当前赔率 + 匹配队名
    print("🎯 解析当前比赛 & 队名匹配...")
    current_matches = []
    for item in odds_raw:
        parsed = parse_odds(item, participants)
        if not parsed:
            continue
        # 尝试匹配到评分系统中的队名
        home_match = fuzzy_match_team(parsed["home_team"], ratings)
        away_match = fuzzy_match_team(parsed["away_team"], ratings)
        parsed["home_rating_name"] = home_match
        parsed["away_rating_name"] = away_match

        # 用匹配到的名称做预测 (匹配不到用默认)
        pred_home = home_match or parsed["home_team"]
        pred_away = away_match or parsed["away_team"]
        pred = predict_match(pred_home, pred_away, ratings)
        parsed["prediction"] = pred

        # 队名显示
        parsed["home_rating"] = (
            f"{home_match} (off={ratings[home_match]['off']}, def={ratings[home_match]['def']})"
            if home_match
            else "无历史数据"
        )
        parsed["away_rating"] = (
            f"{away_match} (off={ratings[away_match]['off']}, def={ratings[away_match]['def']})"
            if away_match
            else "无历史数据"
        )

        # 价值投注
        value_bets = find_value_bets(parsed, pred)
        parsed["value_bets"] = value_bets
        current_matches.append(parsed)

    print(f"   ✅ 解析 {len(current_matches)} 场比赛")
    matched = sum(1 for m in current_matches if m["home_rating_name"] and m["away_rating_name"])
    print(f"   ✅ 其中 {matched} 场匹配到历史评分球队")
    print()

    # Step 4: 当前赔率市场分析
    print("📊 当前赔率市场分析...")
    df_odds = pd.DataFrame(current_matches)
    df_odds["raw_sum"] = (
        1 / df_odds["home_odds"] + 1 / df_odds["draw_odds"] + 1 / df_odds["away_odds"]
    )
    current_odds_analysis = {
        "total_matches": len(df_odds),
        "avg_margin": float(1 - (1 / df_odds["raw_sum"]).mean()),
        "avg_payout": float((1 / df_odds["raw_sum"]).mean()),
        "market_bias": {
            "home_favored": int((df_odds["home_odds"] < df_odds["away_odds"]).sum()),
            "away_favored": int((df_odds["away_odds"] < df_odds["home_odds"]).sum()),
        },
        "implied_home_win_pct": float(((1 / df_odds["home_odds"]) / df_odds["raw_sum"]).mean()),
    }
    print("   ✅ 完成")
    print()

    # Step 5: 合成赔率回测 (从run_live_test逻辑)
    print("📊 运行合成赔率回测...")
    from run_live_test import generate_synthetic_odds, run_analysis

    backtest_rows = []
    for fx in fixtures_parsed:
        if fx["home_goals"] is None or fx["away_goals"] is None:
            continue
        h_odds, d_odds, a_odds = generate_synthetic_odds(fx["home_team"], fx["away_team"], ratings)
        backtest_rows.append(
            {
                "date": fx["date"],
                "home_team": fx["home_team"],
                "away_team": fx["away_team"],
                "home_goals": fx["home_goals"],
                "away_goals": fx["away_goals"],
                "home_odds": h_odds,
                "draw_odds": d_odds,
                "away_odds": a_odds,
            }
        )
    df_bt = pd.DataFrame(backtest_rows)
    backtest_results = run_analysis(df_bt, label="2024赛季合成赔率回测")
    print(
        f"   ✅ {backtest_results['total_matches']} 场回测, 准确率 {backtest_results['market_accuracy']:.1%}"
    )
    print()

    # Step 6: 生成 MD 报告
    print("📝 生成 Markdown 报告...")
    report = generate_report(
        current_matches=current_matches,
        ratings=ratings,
        backtest_results=backtest_results,
        current_odds_analysis=current_odds_analysis,
    )
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"   ✅ 报告已保存到: {REPORT_PATH}")
    print()

    # 汇总
    value_count = sum(1 for m in current_matches if any(vb["is_value"] for vb in m["value_bets"]))
    print("=" * 60)
    print("  ✅ 全部分析完成")
    print("=" * 60)
    print(f"  当前比赛: {len(current_matches)} 场")
    print(f"  有价值投注: {value_count} 场")
    print(f"  报告路径: {REPORT_PATH}")
    print()


if __name__ == "__main__":
    main()
