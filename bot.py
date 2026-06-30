#!/usr/bin/env python3
"""
Telegram 机器人 — 接收消息, 执行分析, 返回结果
用法: python3 bot.py
需要: pip install python-telegram-bot pandas numpy requests
"""

import os
import sys
import traceback
from datetime import datetime, timezone

import requests

import config  # 加载 .env
from engine.five_step import MatchAnalyzer

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_TOKEN:
    print("❌ 未设置 TELEGRAM_BOT_TOKEN")
    sys.exit(1)

analyzer = MatchAnalyzer(os.getenv("ODDSPAPI_KEY", ""))
FD_KEY = config.FOOTBALL_DATA_KEYS[0] if config.FOOTBALL_DATA_KEYS else ""

# ═══════════════════════════════════════════════════
# 命令处理
# ═══════════════════════════════════════════════════


def send_msg(chat_id: int, text: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )


def send_file(chat_id: int, filepath: str, caption: str = ""):
    with open(filepath, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files={"document": f},
            timeout=30,
        )


def cmd_predict(chat_id: int, query: str):
    """单场比赛分析: /分析 England vs Congo DR"""
    query = query.replace("/分析", "").strip()
    if not query or "vs" not in query.lower():
        send_msg(chat_id, "❌ 格式: /分析 法国 vs 瑞典")
        return

    send_msg(chat_id, f"🔍 正在分析: {query}...")

    # 搜索比赛
    today = datetime.now(timezone.utc)
    from datetime import timedelta

    date_from = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")

    parts = query.split(" vs ")
    if len(parts) != 2:
        parts = query.lower().split(" vs ")
    home_q, away_q = parts[0].strip(), parts[1].strip()

    match = None
    for comp in ["WC", "EC", "PL", "BL1", "SA", "PD", "FL1"]:
        try:
            r = requests.get(
                f"https://api.football-data.org/v4/competitions/{comp}/matches",
                params={"dateFrom": date_from, "dateTo": date_to},
                headers={"X-Auth-Token": FD_KEY},
                timeout=10,
            )
            if r.status_code != 200:
                continue
            for m in r.json().get("matches", []):
                h = (m["homeTeam"].get("name") or "").lower()
                a = (m["awayTeam"].get("name") or "").lower()
                if home_q.lower() in h and away_q.lower() in a:
                    match = m
                    break
            if match:
                break
        except Exception:
            pass

    if not match:
        send_msg(chat_id, f"❌ 未找到比赛: {query}")
        return

    # 拉赔率
    odds = None
    try:
        odds_r = requests.get(
            f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds=16&apiKey={os.getenv('ODDSPAPI_KEY', '')}",
            timeout=15,
        )
        parts_api = requests.get(
            f"https://api.oddspapi.io/v4/participants?sportId=10&apiKey={os.getenv('ODDSPAPI_KEY', '')}",
            timeout=15,
        ).json()
        for item in odds_r.json():
            p1 = parts_api.get(str(item.get("participant1Id", "")), "")
            p2 = parts_api.get(str(item.get("participant2Id", "")), "")
            if (
                match["homeTeam"]["name"].lower() in p1.lower()
                and match["awayTeam"]["name"].lower() in p2.lower()
            ):
                bm = item["bookmakerOdds"]["pinnacle"]
                mkt = bm["markets"]["101"]["outcomes"]
                odds = {
                    "home": float(mkt["101"]["players"]["0"]["price"]),
                    "draw": float(mkt["102"]["players"]["0"]["price"]),
                    "away": float(mkt["103"]["players"]["0"]["price"]),
                }
                break
    except Exception:
        pass

    # 五步分析
    match_obj = {
        "match_id": match["id"],
        "home_team": match["homeTeam"]["name"],
        "away_team": match["awayTeam"]["name"],
        "date": match["utcDate"],
        "status": match.get("status", ""),
        "stage": match.get("stage", ""),
        "competition": match.get("competition", {}).get("code", "WC"),
        "competition_name": match.get("competition", {}).get("name", ""),
        "market_odds": odds,
        "tournament_id": 16,
    }

    result = analyzer.analyze(match_obj)

    # 格式化为文本回复
    d = result["details"]
    profile = d["profile"]
    pricing = d["pricing"]
    consensus = d["consensus"]

    text = f"📊 {match['homeTeam']['name']} vs {match['awayTeam']['name']}\n"
    text += f"⏰ {match['utcDate'][:16].replace('T', ' ')} | {match.get('stage', '')}\n\n"

    text += "=" * 30 + "\n"
    text += f"🎯 方向: {result['direction']}\n"
    text += f"📊 置信度: {result['confidence']} | 风险: {result['risk_level']}\n"
    text += f"⭐ 综合评分: {result['total_score']:.0%}\n"
    text += "=" * 30 + "\n\n"

    text += f"① 画像: {profile.get('match_type')} | {profile.get('goal_profile')}\n"
    text += (
        f"② 共识: {consensus.get('consensus_level')} ({consensus.get('consensus_score', 0):.0%})\n"
    )
    text += f"③ 技术: {d['technical'].get('verdict')}\n"
    text += f"④ 定价: 返还率 {pricing.get('pinnacle_payout', 0):.1%}\n"

    ka = pricing.get("kelly_analysis", {})
    if ka:
        text += "\n💰 凯利分析:\n"
        for outcome, v in ka.items():
            k = v["kelly_half"]
            if k > 0.01:
                text += f"  {outcome}: K/2={k:.3f} EV={v['ev']:+.3f} → {v['recommend']}\n"

    if result.get("key_reasons"):
        text += f"\n✅ {'; '.join(result['key_reasons'][:2])}"
    if result.get("warnings"):
        text += f"\n⚠️ {'; '.join(result['warnings'][:2])}"

    text += f"\n\n💡 {result['suggested_action']}"

    send_msg(chat_id, text)


def cmd_today(chat_id: int):
    """今日竞彩全量"""
    send_msg(chat_id, "🔄 正在分析今日竞彩赛事...")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from datetime import timedelta

    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    all_matches = []
    for comp in ["WC", "EC", "PL", "BL1", "SA", "PD", "FL1"]:
        try:
            r = requests.get(
                f"https://api.football-data.org/v4/competitions/{comp}/matches",
                params={"dateFrom": today, "dateTo": tomorrow},
                headers={"X-Auth-Token": FD_KEY},
                timeout=10,
            )
            if r.status_code == 200:
                all_matches.extend(r.json().get("matches", []))
        except Exception:
            pass

    if not all_matches:
        send_msg(chat_id, "📭 今日无赛事")
        return

    text = f"📅 {today} 竞彩赛事\n\n"
    results = []
    for m in all_matches[:10]:  # 最多10场
        mo = {
            "match_id": m["id"],
            "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"],
            "date": m["utcDate"],
            "competition": "WC",
            "competition_name": m.get("competition", {}).get("name", ""),
            "stage": m.get("stage", ""),
            "status": m.get("status", ""),
            "market_odds": None,
            "tournament_id": 16,
        }
        r = analyzer.analyze(mo)
        results.append((m, r))

    for m, r in results:
        t = m["utcDate"][11:16]
        text += f"{t} | {m['homeTeam']['name']} vs {m['awayTeam']['name']}\n"
        text += f"  {r['direction']} | 评分{r['total_score']:.0%} | {r['confidence']} | {r['risk_level']}\n\n"

    send_msg(chat_id, text)


def cmd_help(chat_id: int):
    send_msg(
        chat_id,
        """🤖 Football-Quant 机器人

/分析 法国 vs 瑞典  — 单场五步分析
/分析 法国 vs 瑞典   — 同上（全角空格）
/今日               — 今日全部竞彩
/热门               — 最近热门比赛
/帮助               — 显示此帮助

💡 直接发比赛名称也可以，如「法国 vs 瑞典」
""",
    )


# ═══════════════════════════════════════════════════
# 主循环 — 长轮询
# ═══════════════════════════════════════════════════


def main():
    import time

    import requests

    BASE = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
    print("🤖 机器人启动...")

    # 先清空旧消息
    try:
        r = requests.get(f"{BASE}/getUpdates", params={"offset": -1}, timeout=10)
        updates = r.json().get("result", [])
        if updates:
            offset = updates[-1]["update_id"] + 1
        else:
            offset = 0
    except Exception:
        offset = 0

    print(f"   Offset: {offset} | 等待消息...")

    while True:
        try:
            r = requests.get(
                f"{BASE}/getUpdates", params={"offset": offset, "timeout": 30}, timeout=35
            )
            updates = r.json().get("result", [])

            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message", {})
                chat_id = msg.get("chat", {}).get("id", 0)
                text = (msg.get("text") or "").strip()

                if not text or not chat_id:
                    continue

                print(f"📩 [{chat_id}]: {text}")

                # 路由命令
                if text.startswith("/分析") or text.startswith("／分析"):
                    try:
                        cmd_predict(chat_id, text.replace("／", "/"))
                    except Exception as e:
                        send_msg(chat_id, f"❌ 分析失败: {e}\n{traceback.format_exc()[-300:]}")
                elif (
                    text.startswith("/今日")
                    or text.startswith("／今日")
                    or text == "今日"
                    or text == "竞彩"
                ):
                    try:
                        cmd_today(chat_id)
                    except Exception as e:
                        send_msg(chat_id, f"❌ {e}")
                elif text.startswith("/帮助") or text.startswith("／帮助") or text == "帮助":
                    cmd_help(chat_id)
                elif text.startswith("/start"):
                    send_msg(
                        chat_id,
                        "👋 Football-Quant 已就绪\n\n发送 /帮助 查看可用命令\n发送 /今日 查看今日竞彩",
                    )
                elif " vs " in text.lower() and len(text) < 80:
                    # 自然语言: "法国 vs 瑞典"
                    try:
                        cmd_predict(chat_id, f"/分析 {text}")
                    except Exception as e:
                        send_msg(chat_id, f"❌ {e}")

        except KeyboardInterrupt:
            print("\n👋 机器人关闭")
            break
        except Exception as e:
            print(f"⚠️ {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
