#!/usr/bin/env python3
"""
赛后复盘 — 对比预测 vs 实际结果，保存分析
用法: python3 run_analysis.py [--date YYYY-MM-DD]
输出: reports/YYYY-MM-DD_results.md
"""
import os, sys, json
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import pandas as pd
import requests
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FOOTBALL_DATA_KEYS
from model.trainer import get_model
from utils import get_match_score

FOOTBALL_DATA_KEYS_LIST = FOOTBALL_DATA_KEYS if FOOTBALL_DATA_KEYS else []
BASE_URL = "https://api.football-data.org/v4"
REPORTS_DIR = "/workspace/football-quant-prediction/reports"

LEAGUES = {
    "PL": "英超", "ELC": "英冠", "BL1": "德甲", "SA": "意甲",
    "PD": "西甲", "FL1": "法甲", "DED": "荷甲", "PPL": "葡超",
    "BSA": "巴甲", "CL": "欧冠",
}


def fetch_completed(date_str: str) -> list[dict]:
    """拉取指定日期完成的比赛"""
    all_matches = []
    key_idx = 0
    
    for code, lname in LEAGUES.items():
        key = FOOTBALL_DATA_KEYS_LIST[key_idx % len(FOOTBALL_DATA_KEYS_LIST)]
        key_idx += 1
        
        try:
            url = f"{BASE_URL}/competitions/{code}/matches"
            params = f"?dateFrom={date_str}&dateTo={date_str}&status=FINISHED"
            time.sleep(0.7)
            r = requests.get(url + params, headers={"X-Auth-Token": key}, timeout=15)
            if r.status_code != 200:
                continue
            
            for m in r.json().get("matches", []):
                sc = get_match_score(m.get("score", {}) or {})
                all_matches.append({
                    "league_name": lname,
                    "league_code": code,
                    "match_id": m.get("id"),
                    "date": m.get("utcDate", ""),
                    "home_team": m.get("homeTeam", {}).get("name", ""),
                    "away_team": m.get("awayTeam", {}).get("name", ""),
                    "home_goals": sc["home"],
                    "away_goals": sc["away"],
                })
        except Exception as e:
            print(f"  ⚠️ {lname}: {e}")
    
    return all_matches


def analyze(date_str: str):
    model = get_model()
    
    # 加载当天的预测
    pred_file = f"{REPORTS_DIR}/{date_str}_predictions.json"
    predictions = {}
    if os.path.exists(pred_file):
        with open(pred_file) as f:
            data = json.load(f)
        for m in data.get("matches", []):
            predictions[m["match_id"]] = m
    
    # 拉取实际结果
    print(f"📡 拉取 {date_str} 完赛数据...")
    results = fetch_completed(date_str)
    print(f"   ✅ {len(results)} 场完赛")
    
    if not results:
        print("   无完赛数据，跳过")
        return
    
    # 对比
    correct = 0
    total = 0
    total_abs_error = 0
    brier_sum = 0
    comparison_rows = []
    
    for r in results:
        hg = r.get("home_goals")
        ag = r.get("away_goals")
        if hg is None or ag is None:
            continue
        
        # 实际结果
        if hg > ag:
            actual = "主胜"
        elif hg == ag:
            actual = "平局"
        else:
            actual = "客胜"
        
        # 模型预测
        pred = model.predict(r["home_team"], r["away_team"])
        model_pick = pred["prediction"]
        
        correct += 1 if model_pick == actual else 0
        total += 1
        total_abs_error += abs(pred["home_xg"] - hg) + abs(pred["away_xg"] - ag)
        
        # Brier
        av = {"主胜": (1,0,0), "平局": (0,1,0), "客胜": (0,0,1)}[actual]
        brier_sum += ((pred["p_home"]-av[0])**2 + (pred["p_draw"]-av[1])**2 + (pred["p_away"]-av[2])**2) / 3
        
        comparison_rows.append({
            "league": r["league_name"],
            "home": r["home_team"],
            "away": r["away_team"],
            "score": f"{hg}-{ag}",
            "actual": actual,
            "predicted": model_pick,
            "correct": "✅" if model_pick == actual else "❌",
            "p_home": pred["p_home"],
            "p_draw": pred["p_draw"],
            "p_away": pred["p_away"],
            "xG_home": pred["home_xg"],
            "xG_away": pred["away_xg"],
        })
    
    acc = correct / total if total > 0 else 0
    brier = brier_sum / total if total > 0 else 0
    mae = total_abs_error / (total * 2) if total > 0 else 0
    
    # 生成 MD
    lines = [
        f"# 📊 赛后复盘 — {date_str}",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| 完赛场次 | {total} |",
        f"| 模型准确率 | {acc:.1%} |",
        f"| Brier Score | {brier:.4f} |",
        f"| 平均进球误差 | {mae:.2f} |",
        f"| 主场优势系数 | {model.home_advantage} |",
        "",
        "---",
        "",
        "## 逐场对比",
        "",
        "| 联赛 | 主队 | 客队 | 比分 | 实际 | 预测 | 结果 | 主概率 | 平概率 | 客概率 | xG主 | xG客 |",
        "|------|------|------|------|------|------|------|--------|--------|--------|-------|-------|",
    ]
    
    for row in sorted(comparison_rows, key=lambda x: x["correct"] == "✅"):
        lines.append(
            f"| {row['league']} | {row['home']} | {row['away']} | {row['score']} | "
            f"{row['actual']} | {row['predicted']} | {row['correct']} | "
            f"{row['p_home']:.1%} | {row['p_draw']:.1%} | {row['p_away']:.1%} | "
            f"{row['xG_home']} | {row['xG_away']} |"
        )
    
    # 按联赛统计
    lines.append("")
    lines.append("## 按联赛统计")
    lines.append("")
    lines.append("| 联赛 | 场次 | 准确率 |")
    lines.append("|------|------|--------|")
    league_stats = defaultdict(lambda: {"c": 0, "t": 0})
    for row in comparison_rows:
        league_stats[row["league"]]["t"] += 1
        if row["correct"] == "✅":
            league_stats[row["league"]]["c"] += 1
    for lg, st in sorted(league_stats.items()):
        lines.append(f"| {lg} | {st['t']} | {st['c']/st['t']:.0%} |")
    
    lines.append("")
    lines.append("---")
    lines.append(f"> 🤖 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    report_path = f"{REPORTS_DIR}/{date_str}_results.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"\n📊 {date_str} 复盘完成")
    print(f"   场次: {total} | 准确率: {acc:.1%} | Brier: {brier:.4f}")
    print(f"   📄 {report_path}")
    
    return {"accuracy": acc, "brier": brier, "total": total, "mae": mae}


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()
    
    print("=" * 60)
    print(f"  📊 赛后复盘 — {args.date}")
    print("=" * 60)
    print()
    
    analyze(args.date)


if __name__ == "__main__":
    main()
