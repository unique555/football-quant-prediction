#!/usr/bin/env python3
"""
football-data.co.uk CSV 多线程爬取历史数据库
完全免费, 无需 API Key, 无需登录, 无反爬

用法: python3 scrape_football_data.py
输出: /workspace/football-quant-prediction/data/football_data_co_uk.csv
"""
import os, csv, time, io, threading
from queue import Queue
from datetime import datetime
import requests
import pandas as pd

# ============================================================
# 配置
# ============================================================
DB_PATH = "/workspace/football-quant-prediction/data/football_data_co_uk.csv"
PROGRESS_PATH = "/workspace/football-quant-prediction/data/fdc_progress.json"
THREADS = 4  # 并发线程数

# 联赛代码 → (名称, 简称)
LEAGUES = {
    "E0": ("英超", "eng"),
    "E1": ("英冠", "eng"),
    "E2": ("英甲", "eng"),
    "E3": ("英乙", "eng"),
    "SC0": ("苏超", "sco"),
    "D1": ("德甲", "ger"),
    "D2": ("德乙", "ger"),
    "I1": ("意甲", "ita"),
    "I2": ("意乙", "ita"),
    "SP1": ("西甲", "esp"),
    "SP2": ("西乙", "esp"),
    "F1": ("法甲", "fra"),
    "F2": ("法乙", "fra"),
    "N1": ("荷甲", "ned"),
    "P1": ("葡超", "por"),
    "B1": ("比甲", "bel"),
    "T1": ("土超", "tur"),
    "G1": ("希超", "gre"),
}

# 赛季范围 - football-data.co.uk 命名: 2223 = 2022-23
# 从 1993-94 开始都有数据 (英超最早)
START_YEAR = 2017
END_YEAR = 2025  # 包含 2025-26 赛季

BASE_URL = "https://www.football-data.co.uk/mmz4281"

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}


def season_code(year: int) -> str:
    """2022 → '2223'"""
    return f"{str(year)[-2:]}{str(year+1)[-2:]}"


def fetch_league_csv(league_code: str, season_year: int) -> list[dict]:
    """下载单个联赛赛季 CSV"""
    code = season_code(season_year)
    url = f"{BASE_URL}/{code}/{league_code}.csv"
    
    r = requests.get(url, headers=HEADERS, timeout=30)
    if r.status_code != 200:
        raise Exception(f"HTTP {r.status_code}")
    if not r.text.strip():
        raise Exception("Empty response")
    
    # CSV 解析
    reader = csv.DictReader(io.StringIO(r.text))
    rows = []
    for row in reader:
        # 跳过无效行
        if not row.get("Date") or not row.get("HomeTeam"):
            continue
        
        home_goals = int(row.get("FTHG", 0) or 0)
        away_goals = int(row.get("FTAG", 0) or 0)
        
        # 确定赛果
        if home_goals > away_goals:
            result = "H"
        elif home_goals == away_goals:
            result = "D"
        else:
            result = "A"
        
        rows.append({
            "league_name": LEAGUES[league_code][0],
            "league_code": league_code,
            "season": season_year,
            "date": row.get("Date", ""),
            "time": row.get("Time", ""),
            "home_team": row.get("HomeTeam", ""),
            "away_team": row.get("AwayTeam", ""),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "result": result,
            "ht_home_goals": int(row.get("HTHG", 0) or 0),
            "ht_away_goals": int(row.get("HTAG", 0) or 0),
            "ht_result": row.get("HTR", ""),
            "referee": row.get("Referee", ""),
            "home_shots": int(row.get("HS", 0) or 0),
            "away_shots": int(row.get("AS", 0) or 0),
            "home_shots_target": int(row.get("HST", 0) or 0),
            "away_shots_target": int(row.get("AST", 0) or 0),
            "home_fouls": int(row.get("HF", 0) or 0),
            "away_fouls": int(row.get("AF", 0) or 0),
            "home_corners": int(row.get("HC", 0) or 0),
            "away_corners": int(row.get("AC", 0) or 0),
            "home_yellow": int(row.get("HY", 0) or 0),
            "away_yellow": int(row.get("AY", 0) or 0),
            "home_red": int(row.get("HR", 0) or 0),
            "away_red": int(row.get("AR", 0) or 0),
        })
    
    return rows


def worker(queue: Queue, results: list, progress: dict, lock: threading.Lock, tid: int):
    """爬虫工作线程"""
    prefix = f"[T{tid}]"
    while True:
        try:
            task = queue.get(timeout=5)
        except:
            break
        
        code, lname, year = task
        task_key = f"{code}_{year}"
        
        with lock:
            if task_key in progress["done"]:
                queue.task_done()
                continue
        
        try:
            rows = fetch_league_csv(code, year)
            with lock:
                results.extend(rows)
                progress["done"].add(task_key)
                progress["total"] += len(rows)
            print(f"  {prefix} ✅ {lname} {year}-{year+1}: {len(rows):4d} 场 → 累计 {progress['total']:,}")
        except Exception as e:
            msg = str(e)[:60]
            with lock:
                progress["done"].add(task_key)  # 跳过不可用的
            print(f"  {prefix} ⚪ {lname} {year}-{year+1}: {msg}")
        
        queue.task_done()
        time.sleep(0.3)


def main():
    print("=" * 60)
    print("  📦 football-data.co.uk CSV 批量爬取")
    print(f"  来源:    {BASE_URL}")
    print(f"  线程:    {THREADS}")
    print(f"  联赛:    {len(LEAGUES)} 个")
    print(f"  赛季:    {START_YEAR}-{END_YEAR+1} ({END_YEAR-START_YEAR+1}季)")
    print(f"  完全免费, 无需 Key, 无反爬")
    print("=" * 60)
    print()

    # 加载进度
    progress = {"done": set(), "total": 0}
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH) as f:
            saved = json.load(f)
            progress["done"] = set(saved.get("done", []))
            progress["total"] = saved.get("total", 0)

    # 构建任务
    queue = Queue()
    for code, (lname, _) in LEAGUES.items():
        for year in range(START_YEAR, END_YEAR + 1):
            queue.put((code, lname, year))

    total_tasks = queue.qsize()
    done_count = len(progress["done"])
    print(f"📋 总任务: {total_tasks} | 已完成: {done_count} | 待执行: {total_tasks - done_count}")
    print()

    # 结果
    all_rows = []
    lock = threading.Lock()

    # 启动线程
    threads = []
    for i in range(THREADS):
        t = threading.Thread(target=worker, args=(queue, all_rows, progress, lock, i+1))
        t.daemon = True
        t.start()
        threads.append(t)

    # 等待完成
    import json
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        print("\n⚠️ 中断, 保存中...")

    # 保存
    if all_rows:
        df = pd.DataFrame(all_rows)
        if os.path.exists(DB_PATH):
            existing = pd.read_csv(DB_PATH)
            df = pd.concat([existing, df], ignore_index=True)
        df.to_csv(DB_PATH, index=False)

    with open(PROGRESS_PATH, "w") as f:
        json.dump({"done": list(progress["done"]), "total": progress["total"]}, f)

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
        if 'date' in df.columns:
            dates = df['date'].dropna()
            if len(dates) > 0:
                print(f"  日期:     {dates.min()} ~ {dates.max()}")
        print()
        for name, grp in df.groupby("league_name"):
            print(f"  {name}: {len(grp):5d} 场 ({grp['season'].nunique()} 季)")
    print(f"\n  数据库: {DB_PATH}")


if __name__ == "__main__":
    main()
