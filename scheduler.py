#!/usr/bin/env python3
"""
统一调度器 — 定时运行全流程 + 单场时间点监控
用法:
  python3 scheduler.py                  # 一次性全跑
  python3 scheduler.py --watch           # 持续监控 (每分钟检查一次)
  python3 scheduler.py --watch-match 537416  # 监控单场比赛全时间点

cron 部署 (推荐):
  */30 * * * * cd /path && python3 scheduler.py
  0  9  * * * cd /path && python3 scheduler.py  # 每天早上9点
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import FOOTBALL_DATA_KEYS
from notify import send
from notify import status as notify_status

FD_KEY = FOOTBALL_DATA_KEYS[0] if FOOTBALL_DATA_KEYS else ""

# ── 任务调度表 ──
SCHEDULE = {
    "daily_predict": {"cmd": "python3 run_daily.py", "desc": "每日预测", "interval_h": 24},
    "daily_analysis": {"cmd": "python3 run_analysis.py", "desc": "赛后复盘", "interval_h": 24},
    "weekly_review": {"cmd": "python3 run_weekly.py", "desc": "周度复盘+优化", "interval_h": 168},
    "data_refresh": {
        "cmd": "python3 scrape_football_data.py",
        "desc": "数据刷新",
        "interval_h": 168,
    },
    "model_retrain": {
        "cmd": "python3 -c \"from model.trainer import get_model; m=get_model(); import pandas as pd; df=pd.read_csv('data/football_data_co_uk.csv',low_memory=False); m.train(df,seasons=[2021,2022,2023,2024,2025]); from model.national_trainer import get_national_model; nm=get_national_model(); nm.train(start_year=2018,end_year=2026)\"",
        "desc": "模型重训",
        "interval_h": 168,
    },
}

STATE_FILE = "/workspace/football-quant-prediction/data/scheduler_state.json"


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def should_run(task_name: str, interval_h: int, state: dict) -> bool:
    last = state.get(task_name, {}).get("last_run")
    if not last:
        return True
    last_dt = datetime.fromisoformat(last)
    return (datetime.now() - last_dt).total_seconds() / 3600 >= interval_h


def run_task(task_name: str, config: dict, state: dict) -> bool:
    print(f"\n{'=' * 50}")
    print(f"  🏃 {config['desc']} ({task_name})")
    print(f"{'=' * 50}")
    try:
        result = subprocess.run(
            config["cmd"],
            shell=True,
            cwd="/workspace/football-quant-prediction",
            capture_output=True,
            text=True,
            timeout=600,
        )
        success = result.returncode == 0
        print(result.stdout[-500:] if result.stdout else "(no output)")
        if result.stderr and not success:
            print(f"  STDERR: {result.stderr[-300:]}")

        state[task_name] = {"last_run": datetime.now().isoformat(), "success": success}
        save_state(state)

        # 推送通知
        status_icon = "✅" if success else "❌"
        send(
            f"{status_icon} {config['desc']}: {'完成' if success else '失败'} | {datetime.now().strftime('%H:%M')}"
        )

        return success
    except subprocess.TimeoutExpired:
        print("  ❌ 超时")
        state[task_name] = {"last_run": datetime.now().isoformat(), "success": False}
        save_state(state)
        return False


def watch_matches(interval: int = 300):
    """持续监控比赛: 距开赛 12h/6h/3h/1h/0 各跑一次预测"""
    print("👀 启动比赛监控模式...")
    print(f"   扫描间隔: {interval}秒")

    monitored = {}  # match_id → {last_checkpoint, ...}
    checkpoints = [-720, -360, -180, -60, -15, 0, 15, 45, 90]  # 分钟

    while True:
        try:
            # 拉取未来 7 天比赛
            today = datetime.now(timezone.utc)
            date_from = today.strftime("%Y-%m-%d")
            date_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")

            r = requests.get(
                f"https://api.football-data.org/v4/matches?dateFrom={date_from}&dateTo={date_to}",
                headers={"X-Auth-Token": FD_KEY},
                timeout=15,
            )
            if r.status_code != 200:
                time.sleep(interval)
                continue

            for m in r.json().get("matches", []):
                mid = m["id"]
                kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                mins_to_kickoff = (kickoff - today).total_seconds() / 60

                # 跳过已过期的
                if mins_to_kickoff < -120:
                    continue

                # 初始化监控
                if mid not in monitored:
                    monitored[mid] = {
                        "last_checkpoint": None,
                        "team": f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}",
                    }

                # 检查是否到了下一个 checkpoint
                for cp in sorted(checkpoints):
                    if mins_to_kickoff <= cp and (
                        monitored[mid]["last_checkpoint"] is None
                        or monitored[mid]["last_checkpoint"] > cp
                    ):
                        print(
                            f"\n⏰ [{datetime.now().strftime('%H:%M')}] {monitored[mid]['team']} → checkpoint {cp}min"
                        )
                        subprocess.run(
                            f"python3 predict_match.py --id {mid}",
                            shell=True,
                            cwd="/workspace/football-quant-prediction",
                            timeout=60,
                        )
                        monitored[mid]["last_checkpoint"] = cp
                        send(f"📊 {monitored[mid]['team']}: checkpoint {cp}min 预测完成")
                        break

            # 清理过期监控
            expired = [
                mid
                for mid, data in monitored.items()
                if (
                    kickoff := datetime.fromisoformat(
                        next(
                            (m["utcDate"] for m in r.json().get("matches", []) if m["id"] == mid),
                            "2000-01-01T00:00:00Z",
                        ).replace("Z", "+00:00")
                    )
                )
                and (kickoff - today).total_seconds() / 60 < -120
            ]
            for mid in expired:
                del monitored[mid]

            time.sleep(interval)

        except KeyboardInterrupt:
            print("\n👋 监控停止")
            break
        except Exception as e:
            print(f"  ⚠️ {e}")
            time.sleep(interval)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch", action="store_true", help="持续监控模式")
    parser.add_argument("--watch-match", type=int, help="监控单场比赛")
    parser.add_argument("--now", action="store_true", help="立即执行所有任务")
    args = parser.parse_args()

    if args.watch_match:
        # 单场监控: 循环运行 predict_match
        print(f"👀 监控比赛 {args.watch_match}")
        while True:
            subprocess.run(
                f"python3 predict_match.py --id {args.watch_match}",
                shell=True,
                cwd="/workspace/football-quant-prediction",
                timeout=60,
            )
            print("  ⏳ 15分钟后再次检查...")
            time.sleep(900)

    if args.watch:
        watch_matches()
        return

    # 默认: 按调度表检查并运行
    state = load_state()
    print(f"📋 调度器启动 | 通知: {json.dumps(notify_status())}")

    force = args.now

    for task_name, config in SCHEDULE.items():
        if force or should_run(task_name, config["interval_h"], state):
            run_task(task_name, config, state)
        else:
            last = state.get(task_name, {}).get("last_run", "从未")[:16]
            print(f"  ⏭️  {config['desc']}: 跳过 (上次: {last})")

    print("\n✅ 调度完成 | 下次: python3 scheduler.py")


if __name__ == "__main__":
    main()
