#!/usr/bin/env python3
"""
多联赛批量预测 & 报告生成
用法: python3 predict_all_leagues.py
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
REPORT_PATH = "/workspace/football-quant-prediction/multi_league_report.md"

# ============================================================
# 联赛映射: 名称 → {odds_tournament_id, api_league_id, season}
# season 用 2024 因为这是 API-Football Free 能拉到的最新完整赛季
# ============================================================
LEAGUES = {
    "英超": {"odds_id": 17, "api_id": 39, "season": 2024, "tier": "top5"},
    "英冠": {"odds_id": 18, "api_id": 40, "season": 2024, "tier": "top5"},
    "意甲": {"odds_id": 23, "api_id": 135, "season": 2024, "tier": "top5"},
    "荷甲": {"odds_id": 37, "api_id": 88, "season": 2024, "tier": "top5"},
    "比甲": {"odds_id": 38, "api_id": 144, "season": 2024, "tier": "top5"},
    "苏超": {"odds_id": 36, "api_id": 179, "season": 2024, "tier": "top5"},
    "挪超": {"odds_id": 20, "api_id": 103, "season": 2024, "tier": "europe"},
    "瑞典超": {"odds_id": 40, "api_id": 113, "season": 2024, "tier": "europe"},
    "丹超": {"odds_id": 39, "api_id": 119, "season": 2024, "tier": "europe"},
    "巴甲": {"odds_id": 325, "api_id": 71, "season": 2024, "tier": "americas"},
    "美职联": {"odds_id": 242, "api_id": 253, "season": 2024, "tier": "americas"},
    "欧冠": {"odds_id": 7, "api_id": 2, "season": 2024, "tier": "top5"},
    "欧联": {"odds_id": 679, "api_id": 3, "season": 2024, "tier": "top5"},
    # 以下是休赛期联赛 — 只有历史数据，无当前赔率
    "西甲": {"odds_id": 8, "api_id": 140, "season": 2024, "tier": "top5"},
    "德甲": {"odds_id": 35, "api_id": 78, "season": 2024, "tier": "top5"},
    "法甲": {"odds_id": 34, "api_id": 61, "season": 2024, "tier": "top5"},
}

# ============================================================
# 工具函数
# ============================================================


def safe_request(url, params=None, headers=None, timeout=30, sleep=1):
    time.sleep(sleep)
    r = requests.get(url, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def poisson_pmf(lmbda, k):
    if k < 0:
        return 0.0
    return exp(-lmbda) * (lmbda**k) / factorial(k)


# ============================================================
# 1. OddsPapi — 拉赔率 + 队伍名称
# ============================================================


def fetch_tournament_odds(tournament_id: int) -> list[dict]:
    """拉取联赛赔率，Pinnacle 优先，失败则回退到所有庄家"""
    url_pin = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds={tournament_id}&apiKey={ODDSPAPI_KEY}"
    try:
        return safe_request(url_pin, sleep=2)
    except Exception:
        # 回退: 不限庄家
        url_all = f"https://api.oddspapi.io/v4/odds-by-tournaments?tournamentIds={tournament_id}&apiKey={ODDSPAPI_KEY}"
        try:
            return safe_request(url_all, sleep=2)
        except Exception:
            return []


def fetch_participants() -> dict:
    """拉取足球队名映射 (sportId=10, 全量)"""
    url = f"https://api.oddspapi.io/v4/participants?sportId=10&apiKey={ODDSPAPI_KEY}"
    return safe_request(url, sleep=1)


def parse_odds(item: dict, participants: dict) -> Optional[dict]:
    """解析赔率 — 优先 Pinnacle，否则取第一个可用庄家的 1X2"""
    bm_odds = item.get("bookmakerOdds", {})
    # 优先选 Pinnacle
    bm = bm_odds.get("pinnacle") or next(iter(bm_odds.values()), {}) if bm_odds else {}
    mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
    try:
        h = float(mkt["101"]["players"]["0"]["price"])
        d = float(mkt["102"]["players"]["0"]["price"])
        a = float(mkt["103"]["players"]["0"]["price"])
        p1 = str(item.get("participant1Id", ""))
        p2 = str(item.get("participant2Id", ""))
        return {
            "fixture_id": item["fixtureId"],
            "home_team": participants.get(p1, f"Team_{p1}"),
            "away_team": participants.get(p2, f"Team_{p2}"),
            "home_odds": h,
            "draw_odds": d,
            "away_odds": a,
            "start_time": item.get("startTime", ""),
        }
    except (KeyError, TypeError, AttributeError):
        return None


# ============================================================
# 2. API-Football — 拉赛果
# ============================================================


def fetch_fixtures(league_id: int, season: int) -> list[dict]:
    url = "https://v3.football.api-sports.io/fixtures"
    params = {"league": league_id, "season": season, "status": "FT"}
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    return safe_request(url, params=params, headers=headers, sleep=6).get("response", [])


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
# 3. 球队实力评分
# ============================================================


def build_team_strength(fixtures: list[dict]) -> dict:
    teams = {}
    for fx in fixtures:
        home, away = fx["home_team"], fx["away_team"]
        hg, ag = fx["home_goals"], fx["away_goals"]
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
    avg_gf = all_gf / all_gp if all_gp > 0 else 1.4

    ratings = {}
    for name, s in teams.items():
        ratings[name] = {
            "off": round((s["gf"] / s["gp"]) / avg_gf, 3),
            "def": round((s["ga"] / s["gp"]) / avg_gf, 3),
            "gp": s["gp"],
            "w": s["w"],
            "d": s["d"],
            "l": s["l"],
            "pts": s["w"] * 3 + s["d"],
            "gf": s["gf"],
            "ga": s["ga"],
        }
    return ratings


# ============================================================
# 4. 泊松预测
# ============================================================


def predict_match(home_team: str, away_team: str, ratings: dict) -> dict:
    default = {"off": 1.0, "def": 1.0}
    hr = ratings.get(home_team, default)
    ar = ratings.get(away_team, default)
    home_xg = hr["off"] * ar["def"] * 1.35
    away_xg = ar["off"] * hr["def"] * 0.95

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

    return {
        "home_xg": round(home_xg, 2),
        "away_xg": round(away_xg, 2),
        "p_home": round(p_home, 4),
        "p_draw": round(p_draw, 4),
        "p_away": round(p_away, 4),
    }


def fuzzy_match(op_name: str, ratings: dict) -> Optional[str]:
    op_lower = op_name.lower().replace(" fc", "").replace(" afc", "").replace(" & ", " and ")
    for rname in ratings:
        r_lower = rname.lower().replace(" fc", "").replace(" afc", "")
        if op_lower == r_lower:
            return rname
        if op_lower in r_lower or r_lower in op_lower:
            return rname
    op_words = set(op_lower.split())
    best, best_score = None, 0
    for rname in ratings:
        score = len(op_words & set(rname.lower().split()))
        if score > best_score:
            best_score = score
            best = rname
    return best if best_score >= 1 else None


# ============================================================
# 5. 合成赔率回测
# ============================================================


def synthetic_odds(home: str, away: str, ratings: dict, margin=0.025):
    hr = ratings.get(home, {"off": 1.0, "def": 1.0})
    ar = ratings.get(away, {"off": 1.0, "def": 1.0})
    home_xg = hr["off"] * ar["def"] * 1.35
    away_xg = ar["off"] * hr["def"] * 0.95
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
    return (
        (
            round(1 / (p_home * (1 + margin)), 2) if p_home > 0 else 99.0,
            round(1 / (p_draw * (1 + margin)), 2) if p_draw > 0 else 99.0,
            round(1 / (p_away * (1 + margin)), 2) if p_away > 0 else 99.0,
        ),
        p_home,
        p_draw,
        p_away,
    )


def run_backtest(fixtures: list[dict], ratings: dict) -> dict:
    rows, correct, brier_sum = [], 0, 0.0
    for fx in fixtures:
        if fx["home_goals"] is None or fx["away_goals"] is None:
            continue
        (h_odds, d_odds, a_odds), ph, pd, pa = synthetic_odds(
            fx["home_team"], fx["away_team"], ratings
        )
        actual = (
            "home"
            if fx["home_goals"] > fx["away_goals"]
            else ("draw" if fx["home_goals"] == fx["away_goals"] else "away")
        )
        pred = max([("home", ph), ("draw", pd), ("away", pa)], key=lambda x: x[1])[0]
        correct += 1 if pred == actual else 0
        av = {"home": (1, 0, 0), "draw": (0, 1, 0), "away": (0, 0, 1)}[actual]
        brier_sum += ((ph - av[0]) ** 2 + (pd - av[1]) ** 2 + (pa - av[2]) ** 2) / 3
        rows.append(
            {
                "date": fx["date"],
                "home_team": fx["home_team"],
                "away_team": fx["away_team"],
                "home_goals": fx["home_goals"],
                "away_goals": fx["away_goals"],
                "home_odds": h_odds,
                "draw_odds": d_odds,
                "away_odds": a_odds,
                "actual": actual,
                "pred": pred,
            }
        )
    n = len(rows)
    return {
        "total": n,
        "accuracy": correct / n if n > 0 else 0,
        "brier": brier_sum / n if n > 0 else 0,
        "home_pct": sum(1 for r in rows if r["actual"] == "home") / n if n else 0,
        "draw_pct": sum(1 for r in rows if r["actual"] == "draw") / n if n else 0,
        "away_pct": sum(1 for r in rows if r["actual"] == "away") / n if n else 0,
        "rows": rows,
    }


# ============================================================
# 6. 生成 MD 报告
# ============================================================


def generate_report(all_data: dict) -> str:
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# ⚽ 多联赛量化预测报告",
        "",
        f"> 生成时间: {now}  ",
        "> 数据源: OddsPapi (Pinnacle) + API-Football  ",
        "> 模型: Poisson 分布 × 球队实力评分  ",
        f"> 覆盖联赛: {len(all_data)} 个",
        "",
    ]

    # ---- 联赛总览 ----
    lines.append("## 一、联赛覆盖总览")
    lines.append("")
    lines.append("| 联赛 | 状态 | 当前场次 | 历史赛果 | 回测准确率 |")
    lines.append("|------|------|----------|----------|------------|")
    for name, d in all_data.items():
        status = "🟢 在赛季中" if d["current_matches"] > 0 else "⚫ 休赛期"
        acc = d.get("backtest", {}).get("accuracy", 0)
        lines.append(
            f"| {name} | {status} | {d['current_matches']} | {d['historical_fixtures']} | {acc:.1%} |"
        )
    lines.append("")

    # ---- 当前比赛预测 ----
    has_current = [(n, d) for n, d in all_data.items() if d["current_matches"] > 0]
    if has_current:
        lines.append("## 二、当下比赛预测")
        lines.append("")
        for league_name, d in has_current:
            lines.append(f"### {league_name} ({d['current_matches']} 场)")
            lines.append("")
            for m in d["matches"]:
                pred = m["prediction"]
                raw = 1 / m["home_odds"] + 1 / m["draw_odds"] + 1 / m["away_odds"]
                mph, mpd, mpa = (
                    (1 / m["home_odds"]) / raw,
                    (1 / m["draw_odds"]) / raw,
                    (1 / m["away_odds"]) / raw,
                )
                best = max(
                    [("主胜", pred["p_home"]), ("平局", pred["p_draw"]), ("客胜", pred["p_away"])],
                    key=lambda x: x[1],
                )

                lines.append(f"**{m['home_team']} vs {m['away_team']}**  ")
                lines.append(f"⏰ {m['start_time'][:16].replace('T', ' ')}  ")
                lines.append("")
                lines.append("|  | 主胜 | 平局 | 客胜 |")
                lines.append("|--|------|------|------|")
                lines.append(
                    f"| Pinnacle 赔率 | {m['home_odds']} | {m['draw_odds']} | {m['away_odds']} |"
                )
                lines.append(f"| 市场概率 | {mph:.1%} | {mpd:.1%} | {mpa:.1%} |")
                lines.append(
                    f"| **模型概率** | **{pred['p_home']:.1%}** | **{pred['p_draw']:.1%}** | **{pred['p_away']:.1%}** |"
                )
                lines.append("")
                lines.append(
                    f"🔮 预测: **{best[0]}** ({best[1]:.1%}) | xG: {pred['home_xg']}-{pred['away_xg']} | 返还率: {1 / raw:.1%}"
                )

                # 价值投注标记
                edges = []
                if pred["p_home"] / mph - 1 > 0.05:
                    edges.append(f"主胜 (edge +{pred['p_home'] / mph - 1:.1%})")
                if pred["p_draw"] / mpd - 1 > 0.05:
                    edges.append(f"平局 (edge +{pred['p_draw'] / mpd - 1:.1%})")
                if pred["p_away"] / mpa - 1 > 0.05:
                    edges.append(f"客胜 (edge +{pred['p_away'] / mpa - 1:.1%})")
                if edges:
                    lines.append(f"💎 价值: {', '.join(edges)}")
                lines.append("")
            lines.append("")
    else:
        lines.append("## 二、当下比赛预测")
        lines.append("")
        lines.append("> 当前无进行中赛季的联赛有赔率数据。大部分欧洲顶级联赛处于休赛期。")
        lines.append("")

    # ---- 回测验证 ----
    lines.append("## 三、各联赛回测验证")
    lines.append("")
    lines.append("| 联赛 | 场次 | 准确率 | Brier | 主胜% | 平局% | 客胜% |")
    lines.append("|------|------|--------|-------|-------|-------|-------|")
    for name, d in all_data.items():
        bt = d.get("backtest", {})
        if bt:
            lines.append(
                f"| {name} | {bt['total']} | {bt['accuracy']:.1%} | {bt['brier']:.4f} | {bt['home_pct']:.1%} | {bt['draw_pct']:.1%} | {bt['away_pct']:.1%} |"
            )
    lines.append("")

    # ---- 免责声明 ----
    lines.append("---")
    lines.append("")
    lines.append("## 免责声明")
    lines.append("")
    lines.append("> ⚠️ 本报告仅为量化模型实验输出，**不构成任何投注建议**。")
    lines.append("> 模型使用简化的 Poisson 分布 + 球队评分方法，精度有限。")
    lines.append("> 回测基于合成赔率（非真实市场赔率），仅供参考。")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# 7. 主流程
# ============================================================


def main():
    print("=" * 60)
    print("  ⚽ 多联赛批量预测系统")
    print("=" * 60)
    print()

    # 缓存 participants (只需拉一次)
    print("📡 拉取队伍名称映射...")
    participants = fetch_participants()
    print(f"   ✅ {len(participants)} 支球队")
    print()

    all_data = {}

    for league_name, cfg in LEAGUES.items():
        print(f"{'─' * 50}")
        print(f"  🏆 {league_name} (OddsPapi ID={cfg['odds_id']}, API-Football ID={cfg['api_id']})")
        print(f"{'─' * 50}")

        league_result = {
            "current_matches": 0,
            "historical_fixtures": 0,
            "matches": [],
            "backtest": {},
            "ratings": {},
        }

        # ----- 拉取当前赔率 -----
        try:
            odds_raw = fetch_tournament_odds(cfg["odds_id"])
            current_matches = []
            for item in odds_raw:
                parsed = parse_odds(item, participants)
                if parsed:
                    current_matches.append(parsed)
            league_result["current_matches"] = len(current_matches)
            print(f"   📊 当前赔率: {len(current_matches)} 场")
        except Exception as e:
            print(f"   ⚠️ 赔率拉取失败: {e}")
            current_matches = []

        # ----- 拉取历史赛果 -----
        try:
            fixtures_raw = fetch_fixtures(cfg["api_id"], cfg["season"])
            fixtures = [parse_fixture(f) for f in fixtures_raw]
            league_result["historical_fixtures"] = len(fixtures)
            print(f"   📜 历史赛果: {len(fixtures)} 场")
        except Exception as e:
            print(f"   ⚠️ 赛果拉取失败: {e}")
            fixtures = []

        # ----- 构建评分 & 回测 -----
        if fixtures:
            ratings = build_team_strength(fixtures)
            league_result["ratings"] = ratings
            print(f"   ⭐ 球队评分: {len(ratings)} 队")

            bt = run_backtest(fixtures, ratings)
            league_result["backtest"] = {k: v for k, v in bt.items() if k != "rows"}
            print(f"   📈 回测准确率: {bt['accuracy']:.1%} ({bt['total']}场)")

            # ----- 对当前比赛做预测 -----
            if current_matches:
                for m in current_matches:
                    hm = fuzzy_match(m["home_team"], ratings)
                    am = fuzzy_match(m["away_team"], ratings)
                    pred = predict_match(
                        hm if hm else m["home_team"], am if am else m["away_team"], ratings
                    )
                    m["prediction"] = pred
                    m["home_rating_match"] = hm
                    m["away_rating_match"] = am
                matched = sum(
                    1
                    for m in current_matches
                    if m.get("home_rating_match") and m.get("away_rating_match")
                )
                print(f"   🎯 队名匹配: {matched}/{len(current_matches)}")
                league_result["matches"] = current_matches
        else:
            print("   ⚠️ 无历史数据，跳过评分/预测")

        all_data[league_name] = league_result
        time.sleep(2)  # OddsPapi 速率限制
        print()

    # ----- 生成报告 -----
    print("=" * 60)
    print("📝 生成 Markdown 报告...")
    report = generate_report(all_data)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"   ✅ 报告已保存: {REPORT_PATH}")
    print()

    # ----- 总览 -----
    print("=" * 60)
    print("  📊 执行总结")
    print("=" * 60)
    for name, d in all_data.items():
        bt = d.get("backtest", {})
        has_odds = "🟢" if d["current_matches"] > 0 else "⚫"
        print(
            f"  {has_odds} {name:6s}: 当前{d['current_matches']:2d}场 | 历史{d['historical_fixtures']:3d}场 | 回测{bt.get('accuracy', 0):.0%}"
        )
    print()


if __name__ == "__main__":
    main()
