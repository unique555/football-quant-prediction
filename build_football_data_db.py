#!/usr/bin/env python3
"""
football-data.org 多 Key 多线程历史数据库构建
用法: python3 build_football_data_db.py
输出: /workspace/football-quant-prediction/data/football_data_db.csv

每 Key 一个线程, 各跑 10次/分钟, N Key = N倍速度
"""
import os, json, time, threading, math
from datetime import datetime, timezone
from queue import Queue
from typing import Optional
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FOOTBALL_DATA_KEYS
from utils import get_match_score

# ============================================================
# 配置 — 多 Key 多线程
# ============================================================
API_KEYS = FOOTBALL_DATA_KEYS

DB_PATH = "/workspace/football-quant-prediction/data/football_data_db.csv"
PROGRESS_PATH = "/workspace/football-quant-prediction/data/fd_build_progress.json"

BASE_URL = "https://api.football-data.org/v4"
RATE_INTERVAL = 6.5  # 每次请求间隔秒 (10次/分钟 = 6s, 留余量 6.5s)

# 赛季范围
SEASONS = list(range(2017, 2025))

# 免费计划 12 个联赛
COMPETITIONS = {
    "英超":    "PL",
    "英冠":    "ELC",
    "德甲":    "BL1",
    "意甲":    "SA",
    "西甲":    "PD",
    "法甲":    "FL1",
    "荷甲":    "DED",
    "葡超":    "PPL",
    "巴甲":    "BSA",
    "欧冠":    "CL",
    "世界杯":  "WC",
    "欧洲杯":  "EC",
}


class RateLimiter:
    """每线程独立的速率控制器"""
    def __init__(self):
        self.lock = threading.Lock()
        self.last_request = 0

    def wait(self):
        with self.lock:
            elapsed = time.time() - self.last_request
            if elapsed < RATE_INTERVAL:
                time.sleep(RATE_INTERVAL - elapsed)
            self.last_request = time.time()


def fetch_matches(competition_code: str, season: int, league_name: str, 
                   api_key: str, limiter: RateLimiter, thread_id: int) -> list[dict]:
    """拉取单赛季全部比赛"""
    headers = {"X-Auth-Token": api_key}
    date_from = f"{season}-07-01"
    date_to = f"{season+1}-06-30"
    url = f"{BASE_URL}/competitions/{competition_code}/matches"
    
    limiter.wait()
    r = requests.get(f"{url}?dateFrom={date_from}&dateTo={date_to}", 
                     headers=headers, timeout=30)
    
    if r.status_code == 429:
        print(f"  [T{thread_id}] ⏳ 速率限制, 等待60s...")
        time.sleep(60)
        limiter.wait()
        r = requests.get(f"{url}?dateFrom={date_from}&dateTo={date_to}", 
                        headers=headers, timeout=30)
    
    r.raise_for_status()
    data = r.json()
    
    matches = []
    for m in data.get("matches", []):
        sc = get_match_score(m.get("score", {}) or {})
        matches.append({
            "league_name": league_name,
            "league_code": competition_code,
            "season": season,
            "match_id": m.get("id"),
            "date": m.get("utcDate", ""),
            "status": m.get("status", ""),
            "matchday": m.get("matchday"),
            "home_team": m.get("homeTeam", {}).get("name", ""),
            "away_team": m.get("awayTeam", {}).get("name", ""),
            "home_goals": sc.get("home"),
            "away_goals": sc.get("away"),
            "ht_home_goals": sc.get("ht_home"),
            "ht_away_goals": sc.get("ht_away"),
            "stage": m.get("stage", ""),
            "group": m.get("group", ""),
        })
    return matches


def worker(thread_id: int, api_key: str, queue: Queue, results: list, 
           progress: dict, lock: threading.Lock, done_event: threading.Event):
    """工作线程 — 每线程独立 Key + 独立速率控制"""
    limiter = RateLimiter()
    prefix = f"[T{thread_id}]"
    
    while not done_event.is_set():
        try:
            task = queue.get(timeout=3)
        except:
            continue
        
        league_name, code, season = task
        task_key = f"{code}_{season}"
        
        with lock:
            if task_key in progress["done"]:
                queue.task_done()
                continue
        
        print(f"  {prefix} ⬇️  {league_name} {season}-{season+1}")
        try:
            matches = fetch_matches(code, season, league_name, api_key, limiter, thread_id)
            with lock:
                results.extend(matches)
                progress["done"].add(task_key)
                progress["total_fetched"] += len(matches)
            print(f"  {prefix} ✅ {len(matches):4d} 场 → 总计 {progress['total_fetched']:,}")
        except Exception as e:
            print(f"  {prefix} ❌ {e}")
        
        queue.task_done()


def periodic_save(results: list, lock: threading.Lock):
    """后台定期保存"""
    while True:
        time.sleep(45)
        with lock:
            if results:
                _save_to_db(results)


def _save_to_db(matches: list[dict]) -> int:
    if not matches:
        return 0
    df_new = pd.DataFrame(matches)
    # 去重: 同 match_id 只保留最新
    df_new = df_new.drop_duplicates(subset=["match_id"], keep="last")
    if os.path.exists(DB_PATH):
        existing = pd.read_csv(DB_PATH)
        df = pd.concat([existing, df_new], ignore_index=True)
        df = df.drop_duplicates(subset=["match_id"], keep="last")
    else:
        df = df_new
    df.to_csv(DB_PATH, index=False)
    return len(df)


def main():
    print("=" * 60)
    print("  📦 football-data.org 多线程历史数据库")
    print(f"  Key 数:  {len(API_KEYS)} → {len(API_KEYS)} 线程并发")
    print(f"  赛季:    {SEASONS[0]}-{SEASONS[-1]+1} ({len(SEASONS)}季)")
    print(f"  联赛:    {len(COMPETITIONS)} 个")
    print(f"  速率:    每线程 {60/RATE_INTERVAL:.0f}次/分钟")
    total_speed = len(API_KEYS) * 60 / RATE_INTERVAL
    print(f"  总吞吐:   ~{total_speed:.0f}次/分钟")
    print("=" * 60)
    print()

    # 加载进度
    progress = {"done": set(), "total_fetched": 0}
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            saved = json.load(f)
            progress["done"] = set(saved.get("done", []))
            progress["total_fetched"] = saved.get("total_fetched", 0)

    # 构建任务队列
    queue = Queue()
    for league_name, code in COMPETITIONS.items():
        for season in SEASONS:
            queue.put((league_name, code, season))

    total_tasks = queue.qsize()
    done = len(progress["done"])
    remaining = total_tasks - done
    est_seconds = remaining * RATE_INTERVAL / len(API_KEYS)
    est_minutes = math.ceil(est_seconds / 60)
    print(f"📋 总任务: {total_tasks} | 已完成: {done} | 待执行: {remaining}")
    print(f"⏱️  预估耗时: ~{est_minutes} 分钟 ({len(API_KEYS)}线程)")
    print()

    # 共享资源
    all_matches = []
    lock = threading.Lock()
    done_event = threading.Event()

    # 启动工作线程
    threads = []
    for i, key in enumerate(API_KEYS):
        t = threading.Thread(target=worker, args=(i+1, key, queue, all_matches, 
                                                    progress, lock, done_event))
        t.daemon = True
        t.start()
        threads.append(t)
        print(f"  🧵 线程 {i+1} 已启动 (Key: {key[:10]}...)")

    # 启动保存线程
    saver = threading.Thread(target=periodic_save, args=(all_matches, lock))
    saver.daemon = True
    saver.start()

    print()

    # 等待队列清空
    try:
        queue.join()
        done_event.set()
    except KeyboardInterrupt:
        print("\n⚠️ 中断中...")
        done_event.set()

    # 等待线程结束
    for t in threads:
        t.join(timeout=10)

    # 最终保存
    final_rows = _save_to_db(all_matches)

    # 保存进度
    with open(PROGRESS_PATH, "w") as f:
        json.dump({"done": list(progress["done"]), 
                   "total_fetched": progress["total_fetched"]}, f)

    # 汇总
    print()
    print("=" * 60)
    print("  ✅ 完成!")
    print("=" * 60)
    if os.path.exists(DB_PATH):
        df = pd.read_csv(DB_PATH)
        print(f"  总记录:   {len(df):,}")
        print(f"  联赛数:   {df['league_name'].nunique()}")
        print(f"  赛季:     {sorted(df['season'].unique())}")
        print(f"  日期:     {df['date'].min()[:10]} ~ {df['date'].max()[:10]}")
        print()
        for name, grp in df.groupby("league_name"):
            print(f"  {name:6s}: {len(grp):5d} 场 ({grp['season'].nunique()} 季)")
    print(f"\n  数据库: {DB_PATH}")
    print(f"  下次续跑: python3 build_football_data_db.py")


if __name__ == "__main__":
    main()
