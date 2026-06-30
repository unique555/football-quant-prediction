#!/usr/bin/env python3
"""
历史数据库构建 — 拉取 2017-2024 赛季全量赛果
用法: python3 build_history_db.py
输出: /workspace/football-quant-prediction/data/history_db.csv

分日执行策略:
  Day 1: 五大联赛 (英超/西甲/德甲/意甲/法甲) + 英冠/荷甲/巴甲
  Day 2: 剩余联赛 + 新赛季更新
"""
import os, sys, time, json, random
from datetime import datetime, timezone
from typing import Optional
import pandas as pd
import requests

# ============================================================
# 配置
# ============================================================
# 多 Key 轮换池 (API-Football, 已暂停)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import API_FOOTBALL_KEYS

API_KEYS = API_FOOTBALL_KEYS if API_FOOTBALL_KEYS else []
KEY_INDEX_FILE = "/workspace/football-quant-prediction/data/key_index.txt"

# 代理池
PROXY_POOL_FILE = "/tmp/proxies.json"

DB_PATH = "/workspace/football-quant-prediction/data/history_db.csv"
PROGRESS_PATH = "/workspace/football-quant-prediction/data/build_progress.json"

BASE_URL = "https://v3.football.api-sports.io"

# ---- 代理池管理 ----
_proxy_pool = []
_proxy_blacklist = set()

def _init_proxies():
    global _proxy_pool
    if not _proxy_pool and os.path.exists(PROXY_POOL_FILE):
        with open(PROXY_POOL_FILE) as f:
            raw = json.load(f)
        _proxy_pool = [p for p in raw if p not in _proxy_blacklist]

def get_random_proxy() -> Optional[dict]:
    """返回随机代理 (自动刷新)"""
    global _proxy_pool
    _init_proxies()
    if _proxy_pool:
        p = random.choice(_proxy_pool)
        return {"http": p, "https": p}
    return None

def ban_proxy(proxy_url: str):
    """封禁失效代理"""
    global _proxy_pool, _proxy_blacklist
    _proxy_blacklist.add(proxy_url)
    _proxy_pool = [p for p in _proxy_pool if p != proxy_url]

# ---- Key 管理 ----
def get_active_key():
    if os.path.exists(KEY_INDEX_FILE):
        with open(KEY_INDEX_FILE) as f:
            idx = int(f.read().strip())
    else:
        idx = 0
    return API_KEYS[idx % len(API_KEYS)], idx

def rotate_key(current_idx: int) -> tuple:
    new_idx = current_idx + 1
    if new_idx >= len(API_KEYS):
        raise Exception("所有 API Key 配额均已耗尽！请等待明天重置。")
    with open(KEY_INDEX_FILE, "w") as f:
        f.write(str(new_idx))
    return API_KEYS[new_idx], new_idx

ACTIVE_KEY, _key_idx = get_active_key()
HEADERS = {"x-apisports-key": ACTIVE_KEY}

# 目标赛季范围
START_SEASON = 2022   # Free API 限制: 2022-2024
END_SEASON = 2024

# ============================================================
# 联赛配置 (按优先级分批)
# ============================================================

# 全量联赛 (一次性定义, 脚本自动分天执行)
ALL_LEAGUES = {
    # 五大联赛
    "英超":    {"api_id": 39,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    "西甲":    {"api_id": 140,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    "德甲":    {"api_id": 78,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    "意甲":    {"api_id": 135,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    "法甲":    {"api_id": 61,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    # 其他欧洲主流
    "英冠":    {"api_id": 40,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    "荷甲":    {"api_id": 88,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    "葡超":    {"api_id": 94,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    "苏超":    {"api_id": 179,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    "比甲":    {"api_id": 144,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    "挪超":    {"api_id": 103,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    "瑞典超":  {"api_id": 113,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    "丹超":    {"api_id": 119,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    # 美洲
    "巴甲":    {"api_id": 71,   "seasons": list(range(START_SEASON, END_SEASON+1))},
    "美职联":  {"api_id": 253,  "seasons": list(range(START_SEASON, END_SEASON+1))},
    # 欧战
    "欧冠":    {"api_id": 2,    "seasons": list(range(START_SEASON, END_SEASON+1))},
    "欧联":    {"api_id": 3,    "seasons": list(range(START_SEASON, END_SEASON+1))},
}

CURRENT_BATCH = ALL_LEAGUES  # 断点续传, 配额耗尽自动停


# ============================================================
# 核心函数
# ============================================================

def check_usage() -> dict:
    """查询当前 Key 的 API 用量（走代理）"""
    proxy = get_random_proxy()
    r = requests.get(f"{BASE_URL}/status", headers=HEADERS, timeout=10, proxies=proxy)
    return r.json().get("response", {}).get("requests", {})


def switch_key() -> bool:
    """切换下一个 Key，返回是否成功"""
    global ACTIVE_KEY, HEADERS, _key_idx
    try:
        new_key, _key_idx = rotate_key(_key_idx)
        ACTIVE_KEY = new_key
        HEADERS = {"x-apisports-key": ACTIVE_KEY}
        print(f"   🔄 切换 API Key → {ACTIVE_KEY[:10]}...")
        return True
    except Exception as e:
        print(f"   ❌ {e}")
        return False


def load_progress() -> dict:
    """加载断点续传进度"""
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            return json.load(f)
    return {"completed": {}, "total_fetched": 0, "last_updated": ""}


def save_progress(progress: dict):
    progress["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(PROGRESS_PATH, "w") as f:
        json.dump(progress, f, indent=2)


def fetch_season_fixtures(league_id: int, season: int, league_name: str) -> list[dict]:
    """拉取单赛季全部赛果 (走随机代理)"""
    params = {"league": league_id, "season": season}
    proxy = get_random_proxy()
    time.sleep(6.5)
    r = requests.get(f"{BASE_URL}/fixtures", params=params, headers=HEADERS, timeout=30, proxies=proxy)
    data = r.json()
    
    # 检查API错误
    if data.get("errors") and any(v for v in data["errors"].values() if v):
        error_msg = "; ".join(f"{k}={v}" for k, v in data["errors"].items() if v)
        raise Exception(f"API Error: {error_msg}")
    
    items = data.get("response", [])
    all_fixtures = []
    for item in items:
        f = item.get("fixture", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        score = item.get("score", {})
        all_fixtures.append({
            "league_name": league_name,
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
            "venue": f.get("venue", {}).get("name", ""),
            "referee": f.get("referee", ""),
        })
    print(f"     ✅ {len(all_fixtures)} matches")
    return all_fixtures


def append_to_db(fixtures: list[dict]):
    """增量写入CSV"""
    df = pd.DataFrame(fixtures)
    if os.path.exists(DB_PATH):
        existing = pd.read_csv(DB_PATH)
        # 去重：同一fixture_id只保留最新
        df = pd.concat([existing, df], ignore_index=True)
        df = df.drop_duplicates(subset=["fixture_id"], keep="last")
    df.to_csv(DB_PATH, index=False)
    return len(df)


def main():
    print("=" * 60)
    print("  📦 历史数据库构建")
    print(f"  赛季范围: {START_SEASON}-{END_SEASON}")
    print(f"  目标联赛: {len(CURRENT_BATCH)} 个")
    print("=" * 60)
    print()

    # 查用量
    usage = check_usage()
    remaining = usage.get("limit_day", 100) - usage.get("current", 0)
    print(f"📊 API 用量: {usage.get('current', '?')}/{usage.get('limit_day', '?')} (剩余 {remaining})")
    print()

    # 加载进度
    progress = load_progress()
    completed = progress.get("completed", {})

    # 计算总任务
    total_tasks = sum(len(cfg["seasons"]) for cfg in CURRENT_BATCH.values())
    done_tasks = sum(len(v) for v in completed.values())
    print(f"📋 总任务: {total_tasks} 赛季 | 已完成: {done_tasks} | 待执行: {total_tasks - done_tasks}")
    print(f"⏱️  预估耗时: ~{(total_tasks - done_tasks) * 7} 秒")
    print()

    total_new = 0

    for league_name, cfg in CURRENT_BATCH.items():
        league_id = cfg["api_id"]
        done_seasons = set(completed.get(league_name, []))

        for season in cfg["seasons"]:
            if season in done_seasons:
                print(f"⏭️  {league_name} {season}-{season+1} — 已跳过")
                continue

            # 查验剩余配额
            usage = check_usage()
            remaining = usage.get("limit_day", 100) - usage.get("current", 0)
            if remaining <= 2:
                print(f"\n⚠️ Key {ACTIVE_KEY[:10]}... 配额耗尽 (剩余 {remaining})，尝试切换...")
                if switch_key():
                    print(f"   ✅ 已切换，继续拉取\n")
                    continue
                else:
                    print(f"   所有 Key 已用完，保存进度退出...")
                    save_progress(progress)
                    _print_summary(progress)
                    return
            if remaining <= 5:
                print(f"   ⚡ Key {ACTIVE_KEY[:10]}... 配额紧张 (剩余 {remaining})")

            print(f"⬇️  {league_name} {season}-{season+1} (ID={league_id})")
            try:
                fixtures = fetch_season_fixtures(league_id, season, league_name)
                if fixtures:
                    total_rows = append_to_db(fixtures)
                    print(f"     💾 数据库总计: {total_rows} 行")
                else:
                    print(f"     ⚪ 无数据 (赛季可能未开始或API不支持)")

                # 更新进度
                if league_name not in completed:
                    completed[league_name] = []
                completed[league_name].append(season)
                progress["completed"] = completed
                progress["total_fetched"] = progress.get("total_fetched", 0) + len(fixtures)
                total_new += len(fixtures)
                save_progress(progress)

            except Exception as e:
                err_str = str(e)
                print(f"     ❌ 失败: {e}")
                save_progress(progress)
                # 账号暂停 → 切换 Key
                if "suspended" in err_str.lower() or "access" in err_str.lower():
                    print(f"     🚫 Key {ACTIVE_KEY[:10]}... 被暂停，尝试切换...")
                    if switch_key():
                        continue
                    else:
                        save_progress(progress)
                        _print_summary(progress)
                        return
                # 速率限制 → 等待重试
                elif "429" in err_str or "rate" in err_str.lower():
                    print("     ⏳ 速率限制，等待30秒...")
                    time.sleep(30)
                    try:
                        fixtures = fetch_season_fixtures(league_id, season, league_name)
                        if fixtures:
                            total_rows = append_to_db(fixtures)
                            completed.setdefault(league_name, []).append(season)
                            progress["completed"] = completed
                            total_new += len(fixtures)
                            save_progress(progress)
                    except Exception as e2:
                        err_str2 = str(e2)
                        if "suspended" in err_str2.lower() or "access" in err_str2.lower():
                            print(f"     🚫 Key 被暂停，切换...")
                            if switch_key():
                                continue
                        print(f"     ❌ 重试仍失败: {e2}")
                        save_progress(progress)
                        return
                else:
                    save_progress(progress)
                    return

            print()

    print("=" * 60)
    print("  ✅ 本批次全部完成!")
    save_progress(progress)
    _print_summary(progress)


def _print_summary(progress: dict):
    completed = progress.get("completed", {})
    df = pd.read_csv(DB_PATH) if os.path.exists(DB_PATH) else pd.DataFrame()
    print()
    print("=" * 60)
    print("  📊 数据库概览")
    print("=" * 60)
    if not df.empty:
        print(f"  总记录数:   {len(df):,}")
        print(f"  覆盖联赛:   {df['league_name'].nunique()}")
        print(f"  覆盖赛季:   {sorted(df['season'].unique())}")
        print(f"  日期范围:   {df['date'].min()[:10]} ~ {df['date'].max()[:10]}")
        print()
        per_league = df.groupby("league_name").agg(
            seasons=("season", "nunique"),
            matches=("fixture_id", "count"),
        ).sort_values("matches", ascending=False)
        for name, row in per_league.iterrows():
            done = len(completed.get(name, []))
            print(f"  {name:6s}: {int(row['matches']):5d} 场 | {int(row['seasons'])} 赛季 | 今日完成 {done}")
    print(f"\n  数据库路径: {DB_PATH}")
    print()


if __name__ == "__main__":
    main()
