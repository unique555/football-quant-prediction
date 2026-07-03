#!/usr/bin/env python3
"""
API-Football Pro 历史数据库构建 — 2017-2024 全赛季
单 Key, 7500次/天
"""

import json
import os
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import API_FOOTBALL_KEYS

# ═══════════════════════════════════════════════
API_KEY = API_FOOTBALL_KEYS[0] if API_FOOTBALL_KEYS else os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = "https://v3.football.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}
DB_PATH = "/workspace/football-quant-prediction/data/history_db.csv"
PROGRESS_PATH = "/workspace/football-quant-prediction/data/build_progress.json"

START_SEASON = 2017
END_SEASON = 2024

LEAGUES = {
    "英超": 39,
    "西甲": 140,
    "德甲": 78,
    "意甲": 135,
    "法甲": 61,
    "英冠": 40,
    "荷甲": 88,
    "葡超": 94,
    "苏超": 179,
    "比甲": 144,
    "挪超": 103,
    "瑞典超": 113,
    "丹超": 119,
    "巴甲": 71,
    "美职联": 253,
    "欧冠": 2,
    "欧联": 3,
}
# ═══════════════════════════════════════════════


def fetch_season(league_id: int, season: int) -> list[dict]:
    time.sleep(6.5)
    r = requests.get(
        f"{BASE_URL}/fixtures",
        params={"league": league_id, "season": season},
        headers=HEADERS,
        timeout=30,
    )
    if r.status_code == 429:
        print("     ⏳ 限速, 等60s...")
        time.sleep(60)
        r = requests.get(
            f"{BASE_URL}/fixtures",
            params={"league": league_id, "season": season},
            headers=HEADERS,
            timeout=30,
        )

    data = r.json()
    errs = data.get("errors", {})
    if errs and any(v for v in errs.values() if v):
        raise Exception("; ".join(f"{k}={v}" for k, v in errs.items() if v))

    rows = []
    for item in data.get("response", []):
        f = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        score = item.get("score", {})
        rows.append(
            {
                "league_id": league_id,
                "season": season,
                "fixture_id": f.get("id"),
                "date": f.get("date", ""),
                "home_team": teams.get("home", {}).get("name", ""),
                "away_team": teams.get("away", {}).get("name", ""),
                "home_goals": goals.get("home"),
                "away_goals": goals.get("away"),
                "ht_home_goals": score.get("halftime", {}).get("home"),
                "ht_away_goals": score.get("halftime", {}).get("away"),
                "status": f.get("status", {}).get("short", ""),
                "round": item.get("league", {}).get("round", ""),
                "referee": f.get("referee", ""),
            }
        )
    return rows


def main():
    if not API_KEY:
        print("❌ 未设置 API Key")
        return

    print("=" * 60)
    print("  📦 API-Football Pro 历史数据库")
    print(f"  赛季: {START_SEASON}-{END_SEASON + 1} | 联赛: {len(LEAGUES)}")
    print(f"  Key: {API_KEY[:10]}... | Pro 7500/天")
    print("=" * 60)

    progress = {"done": set(), "total": 0}
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            saved = json.load(f)
            progress["done"] = set(saved.get("done", []))
            progress["total"] = saved.get("total", 0)

    total = len(LEAGUES) * (END_SEASON - START_SEASON + 1)
    done = len(progress["done"])
    print(
        f"\n📋 总: {total} | 完成: {done} | 剩余: {total - done} | 预估: ~{(total - done) * 7 // 60}min"
    )
    print()

    for lname, lid in LEAGUES.items():
        for season in range(START_SEASON, END_SEASON + 1):
            key = f"{lid}_{season}"
            if key in progress["done"]:
                continue

            print(f"  ⬇️  {lname} {season}-{season + 1}")
            try:
                rows = fetch_season(lid, season)
                if rows:
                    df_new = pd.DataFrame(rows)
                    if os.path.exists(DB_PATH):
                        existing = pd.read_csv(DB_PATH)
                        df = pd.concat([existing, df_new], ignore_index=True)
                        df = df.drop_duplicates(subset=["fixture_id"], keep="last")
                    else:
                        df = df_new
                    df.to_csv(DB_PATH, index=False)
                progress["done"].add(key)
                progress["total"] += len(rows)
                print(f"     ✅ {len(rows)} 场 | 累计 {progress['total']:,}")
                with open(PROGRESS_PATH, "w") as f:
                    json.dump({"done": list(progress["done"]), "total": progress["total"]}, f)
            except Exception as e:
                print(f"     ❌ {e}")
                with open(PROGRESS_PATH, "w") as f:
                    json.dump({"done": list(progress["done"]), "total": progress["total"]}, f)

    print(f"\n✅ 完成! {progress['total']:,} 场 → {DB_PATH}")


if __name__ == "__main__":
    main()
