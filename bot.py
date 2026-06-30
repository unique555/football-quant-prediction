#!/usr/bin/env python3
"""
Telegram 机器人 — 接收消息, 执行分析, 返回结果
用法: python3 bot.py
需要: pip install python-telegram-bot pandas numpy requests
"""

import os
import sys
import traceback
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import requests

import config  # 加载 .env
from engine.five_step import MatchAnalyzer

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
if not TELEGRAM_TOKEN:
    print("❌ 未设置 TELEGRAM_BOT_TOKEN")
    sys.exit(1)

analyzer = MatchAnalyzer("")
API_FOOTBALL_KEY = config.API_FOOTBALL_KEYS[0] if config.API_FOOTBALL_KEYS else ""
API_FOOTBALL_BASE = f"https://{config.API_FOOTBALL_HOST}"


def api_football_get(path: str, params: dict | None = None) -> dict:
    """API-Football GET helper."""
    if not API_FOOTBALL_KEY:
        return {"errors": {"key": "API_FOOTBALL_KEYS 未配置"}, "response": []}
    try:
        resp = requests.get(
            f"{API_FOOTBALL_BASE}/{path.lstrip('/')}",
            params=params or {},
            headers={"x-apisports-key": API_FOOTBALL_KEY},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        return {"errors": {"request": str(exc)}, "response": []}


def normalize_team_name(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


def team_match_score(query: str, candidate: str) -> float:
    q = normalize_team_name(query)
    c = normalize_team_name(candidate)
    if not q or not c:
        return 0.0
    if q in c or c in q:
        return 1.0
    return SequenceMatcher(None, q, c).ratio()


def split_vs_query(query: str) -> tuple[str, str] | None:
    query = query.strip()
    for marker in [" vs ", " VS ", " Vs ", " v ", " V ", " 对 ", "vs"]:
        if marker in query:
            left, right = query.split(marker, 1)
            left, right = left.strip(), right.strip()
            if left and right:
                return left, right
    return None


def find_api_football_match(home_q: str, away_q: str) -> dict | None:
    """Search API-Football fixtures by date window and fuzzy team names."""
    today = datetime.now(timezone.utc)
    best_match = None
    best_score = 0.0

    for delta in range(-7, 8):
        date_str = (today + timedelta(days=delta)).strftime("%Y-%m-%d")
        data = api_football_get(
            "/fixtures",
            {
                "date": date_str,
                "timezone": "Asia/Shanghai",
            },
        )
        for item in data.get("response", []):
            teams = item.get("teams", {})
            home_name = teams.get("home", {}).get("name", "")
            away_name = teams.get("away", {}).get("name", "")
            score = (team_match_score(home_q, home_name) + team_match_score(away_q, away_name)) / 2
            if score > best_score:
                best_score = score
                best_match = item
            if score >= 0.86:
                return item

    return best_match if best_score >= 0.72 else None


def get_api_football_match_winner_odds(fixture_id: int) -> dict | None:
    """Fetch 1X2 odds from API-Football. bet=1 is Match Winner."""
    data = api_football_get("/odds", {"fixture": fixture_id, "bet": 1})
    response = data.get("response", [])
    if not response:
        return None

    best = None
    best_bookmaker = ""
    preferred_bookmakers = ["Pinnacle", "Bet365", "Betfair", "10Bet"]
    bookmakers = response[0].get("bookmakers", [])
    bookmakers = sorted(
        bookmakers,
        key=lambda bm: (
            preferred_bookmakers.index(bm.get("name", ""))
            if bm.get("name", "") in preferred_bookmakers
            else len(preferred_bookmakers)
        ),
    )

    for bookmaker in bookmakers:
        for bet in bookmaker.get("bets", []):
            if bet.get("id") != 1:
                continue
            odds = {}
            for value in bet.get("values", []):
                side = str(value.get("value", "")).lower()
                odd = value.get("odd")
                if side == "home":
                    odds["home"] = float(odd)
                elif side == "draw":
                    odds["draw"] = float(odd)
                elif side == "away":
                    odds["away"] = float(odd)
            if {"home", "draw", "away"} <= odds.keys():
                best = odds
                best_bookmaker = bookmaker.get("name", "")
                break
        if best:
            break

    if not best:
        return None
    best["bookmaker"] = best_bookmaker
    best["source"] = "api-football"
    return best


def to_match_obj(item: dict, odds: dict | None) -> dict:
    fixture = item.get("fixture", {})
    league = item.get("league", {})
    teams = item.get("teams", {})
    return {
        "match_id": fixture.get("id"),
        "home_team": teams.get("home", {}).get("name", ""),
        "away_team": teams.get("away", {}).get("name", ""),
        "date": fixture.get("date", ""),
        "status": fixture.get("status", {}).get("short", ""),
        "stage": league.get("round", ""),
        "competition": league.get("name", ""),
        "competition_name": league.get("name", ""),
        "market_odds": odds,
        "tournament_id": league.get("id"),
    }


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
    parts = split_vs_query(query)
    if not query or not parts:
        send_msg(chat_id, "❌ 格式: /分析 法国 vs 瑞典")
        return

    send_msg(chat_id, f"🔍 正在分析: {query}...")

    home_q, away_q = parts
    match = find_api_football_match(home_q, away_q)

    if not match:
        send_msg(chat_id, f"❌ API-Football 未找到比赛: {query}")
        return

    fixture_id = match.get("fixture", {}).get("id")
    odds = get_api_football_match_winner_odds(fixture_id) if fixture_id else None
    match_obj = to_match_obj(match, odds)

    result = analyzer.analyze(match_obj)

    # 格式化为文本回复
    d = result["details"]
    profile = d["profile"]
    pricing = d["pricing"]
    consensus = d["consensus"]

    text = f"📊 {match_obj['home_team']} vs {match_obj['away_team']}\n"
    text += f"⏰ {match_obj['date'][:16].replace('T', ' ')} | {match_obj.get('stage', '')}\n"
    if odds:
        text += (
            f"📈 API-Football赔率({odds.get('bookmaker', '?')}): "
            f"{odds['home']}/{odds['draw']}/{odds['away']}\n\n"
        )
    else:
        text += "📈 API-Football 暂无胜平负赔率\n\n"

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
    send_msg(chat_id, "🔄 正在用 API-Football 分析今日赛事...")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data = api_football_get("/fixtures", {"date": today, "timezone": "Asia/Shanghai"})
    all_matches = data.get("response", [])

    if not all_matches:
        send_msg(chat_id, "📭 今日无赛事")
        return

    text = f"📅 {today} 竞彩赛事\n\n"
    results = []
    for m in all_matches[:10]:  # 最多10场
        fixture_id = m.get("fixture", {}).get("id")
        odds = get_api_football_match_winner_odds(fixture_id) if fixture_id else None
        mo = to_match_obj(m, odds)
        r = analyzer.analyze(mo)
        results.append((mo, odds, r))

    for m, odds, r in results:
        t = m["date"][11:16]
        text += f"{t} | {m['home_team']} vs {m['away_team']}\n"
        if odds:
            text += (
                f"  赔率 {odds['home']}/{odds['draw']}/{odds['away']} ({odds.get('bookmaker')})\n"
            )
        else:
            text += "  暂无 API-Football 胜平负赔率\n"
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
