#!/usr/bin/env python3
"""
Telegram 机器人 — 接收消息, 执行分析, 返回结果
用法: python3 bot.py
需要: pip install python-telegram-bot pandas numpy requests
"""

import os
import re
import sys
import traceback
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from functools import lru_cache

import requests

import config  # 加载 .env
from engine.five_step import MatchAnalyzer

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
analyzer = MatchAnalyzer("")
API_FOOTBALL_KEY = config.API_FOOTBALL_KEYS[0] if config.API_FOOTBALL_KEYS else ""
API_FOOTBALL_BASE = f"https://{config.API_FOOTBALL_HOST}"
SHANGHAI_TZ = timezone(timedelta(hours=8))

FINISHED_STATUSES = {"FT", "AET", "PEN", "CANC", "PST", "ABD", "AWD", "WO"}
MAJOR_LEAGUE_IDS = {
    1,  # World Cup
    2,  # UEFA Champions League
    3,  # UEFA Europa League
    4,  # Euro Championship
    5,  # UEFA Nations League
    9,  # Copa America
    15,  # FIFA Club World Cup
    39,  # Premier League
    61,  # Ligue 1
    78,  # Bundesliga
    135,  # Serie A
    140,  # La Liga
}
POPULAR_LEAGUE_KEYWORDS = (
    "world cup",
    "euro",
    "champions league",
    "europa league",
    "premier league",
    "la liga",
    "serie a",
    "bundesliga",
    "ligue 1",
    "copa america",
    "club world cup",
)


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


RAW_TEAM_ALIASES = {
    # 国家队
    "法国": "France",
    "瑞典": "Sweden",
    "荷兰": "Netherlands",
    "英格兰": "England",
    "西班牙": "Spain",
    "德国": "Germany",
    "意大利": "Italy",
    "葡萄牙": "Portugal",
    "比利时": "Belgium",
    "克罗地亚": "Croatia",
    "丹麦": "Denmark",
    "挪威": "Norway",
    "芬兰": "Finland",
    "波兰": "Poland",
    "罗马尼亚": "Romania",
    "土耳其": "Türkiye",
    "希腊": "Greece",
    "瑞士": "Switzerland",
    "奥地利": "Austria",
    "捷克": "Czech Republic",
    "乌克兰": "Ukraine",
    "塞尔维亚": "Serbia",
    "斯洛文尼亚": "Slovenia",
    "斯洛伐克": "Slovakia",
    "匈牙利": "Hungary",
    "保加利亚": "Bulgaria",
    "阿尔巴尼亚": "Albania",
    "波黑": "Bosnia & Herzegovina",
    "摩洛哥": "Morocco",
    "塞内加尔": "Senegal",
    "突尼斯": "Tunisia",
    "加纳": "Ghana",
    "尼日利亚": "Nigeria",
    "喀麦隆": "Cameroon",
    "埃及": "Egypt",
    "阿尔及利亚": "Algeria",
    "科特迪瓦": "Ivory Coast",
    "南非": "South Africa",
    "马里": "Mali",
    "巴西": "Brazil",
    "阿根廷": "Argentina",
    "乌拉圭": "Uruguay",
    "智利": "Chile",
    "哥伦比亚": "Colombia",
    "秘鲁": "Peru",
    "厄瓜多尔": "Ecuador",
    "巴拉圭": "Paraguay",
    "墨西哥": "Mexico",
    "美国": "USA",
    "加拿大": "Canada",
    "哥斯达黎加": "Costa Rica",
    "牙买加": "Jamaica",
    "中国": "China",
    "日本": "Japan",
    "韩国": "South Korea",
    "朝鲜": "North Korea",
    "澳大利亚": "Australia",
    "伊朗": "Iran",
    "沙特": "Saudi Arabia",
    "沙特阿拉伯": "Saudi Arabia",
    "卡塔尔": "Qatar",
    "阿联酋": "United Arab Emirates",
    "伊拉克": "Iraq",
    "约旦": "Jordan",
    "乌兹别克斯坦": "Uzbekistan",
    "泰国": "Thailand",
    "越南": "Vietnam",
    "印尼": "Indonesia",
    "印度尼西亚": "Indonesia",
    "马来西亚": "Malaysia",
    # 常见女足写法
    "法国女足": "France W",
    "瑞典女足": "Sweden W",
    "英格兰女足": "England W",
    "西班牙女足": "Spain W",
    "德国女足": "Germany W",
    "美国女足": "USA W",
    "日本女足": "Japan W",
    "中国女足": "China W",
    # 用户近期提到的俱乐部
    "vps": "VPS",
    "瓦萨": "VPS",
    "vps瓦萨": "VPS",
    "瓦萨vps": "VPS",
    "图尔库国际": "Inter Turku",
    "国际图尔库": "Inter Turku",
    "英特土尔库": "Inter Turku",
    "英特图尔库": "Inter Turku",
}
TEAM_ALIASES = {normalize_team_name(k): v for k, v in RAW_TEAM_ALIASES.items()}
TEAM_SUFFIXES = ("国家队", "男足", "足球队", "队")


def canonical_team_query(name: str) -> str:
    cleaned = name.strip()
    compact = normalize_team_name(cleaned)
    if compact in TEAM_ALIASES:
        return TEAM_ALIASES[compact]

    for suffix in TEAM_SUFFIXES:
        if cleaned.endswith(suffix):
            stripped = cleaned[: -len(suffix)].strip()
            alias = TEAM_ALIASES.get(normalize_team_name(stripped))
            if alias:
                return alias

    return cleaned


def team_name_variants(name: str) -> list[str]:
    cleaned = name.strip()
    canonical = canonical_team_query(cleaned)
    variants = [canonical]
    if cleaned and normalize_team_name(cleaned) != normalize_team_name(canonical):
        variants.append(cleaned)
    return variants


def team_match_score(query: str, candidate: str) -> float:
    best = 0.0
    for query_variant in team_name_variants(query):
        q = normalize_team_name(query_variant)
        c = normalize_team_name(candidate)
        if not q or not c:
            continue
        if q in c or c in q:
            return 1.0
        best = max(best, SequenceMatcher(None, q, c).ratio())
    return best


def split_vs_query(query: str) -> tuple[str, str] | None:
    query = query.strip()
    marker = re.search(r"(对阵|对|(?<![A-Za-z])vs\.?(?![A-Za-z])|\s+v\s+)", query, re.I)
    if marker:
        left = query[: marker.start()].strip()
        right = query[marker.end() :].strip()
        if left and right:
            return left, right
    return None


def fixture_match_score(item: dict, home_q: str, away_q: str) -> float:
    teams = item.get("teams", {})
    home_name = teams.get("home", {}).get("name", "")
    away_name = teams.get("away", {}).get("name", "")
    direct = (team_match_score(home_q, home_name) + team_match_score(away_q, away_name)) / 2
    reverse = (team_match_score(home_q, away_name) + team_match_score(away_q, home_name)) / 2
    return max(direct, reverse)


def parse_fixture_datetime(item: dict) -> datetime | None:
    date_text = item.get("fixture", {}).get("date", "")
    if not date_text:
        return None
    try:
        return datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone(SHANGHAI_TZ)
    except ValueError:
        return None


def fixture_time_rank(item: dict) -> float:
    fixture_dt = parse_fixture_datetime(item)
    if not fixture_dt:
        return 30.0
    return abs((fixture_dt - datetime.now(SHANGHAI_TZ)).total_seconds()) / 86400


@lru_cache(maxsize=256)
def get_api_football_team_id(query: str) -> int | None:
    team_query = canonical_team_query(query)
    data = api_football_get("/teams", {"search": team_query})
    best_id = None
    best_score = 0.0

    for item in data.get("response", []):
        team = item.get("team", {})
        name = team.get("name", "")
        score = team_match_score(team_query, name)
        if normalize_team_name(team_query) == normalize_team_name(name):
            score += 0.05
        if score > best_score:
            best_score = score
            best_id = team.get("id")

    return best_id if best_id and best_score >= 0.72 else None


def find_api_football_match_by_team(home_q: str, away_q: str) -> dict | None:
    team_ids = [
        team_id
        for team_id in (get_api_football_team_id(home_q), get_api_football_team_id(away_q))
        if team_id
    ]
    best_match = None
    best_rank = -1.0
    best_score = 0.0
    seen_fixtures = set()

    for team_id in dict.fromkeys(team_ids):
        for mode, limit in (("next", 60), ("last", 30)):
            data = api_football_get(
                "/fixtures",
                {
                    "team": team_id,
                    mode: limit,
                    "timezone": "Asia/Shanghai",
                },
            )
            for item in data.get("response", []):
                fixture_id = item.get("fixture", {}).get("id")
                if fixture_id in seen_fixtures:
                    continue
                seen_fixtures.add(fixture_id)

                score = fixture_match_score(item, home_q, away_q)
                rank = score - min(fixture_time_rank(item), 30.0) * 0.005
                if score >= 0.72 and rank > best_rank:
                    best_match = item
                    best_rank = rank
                    best_score = score
                elif not best_match and score > best_score:
                    best_match = item
                    best_score = score
                if score >= 0.96 and fixture_time_rank(item) <= 2:
                    return item

    return best_match if best_match and best_score >= 0.72 else None


def find_api_football_match(home_q: str, away_q: str) -> dict | None:
    """Search API-Football fixtures by date window and fuzzy team names."""
    home_q = canonical_team_query(home_q)
    away_q = canonical_team_query(away_q)
    today = datetime.now(SHANGHAI_TZ)
    best_match = None
    best_score = 0.0

    for delta in range(-7, 15):
        date_str = (today + timedelta(days=delta)).strftime("%Y-%m-%d")
        data = api_football_get(
            "/fixtures",
            {
                "date": date_str,
                "timezone": "Asia/Shanghai",
            },
        )
        for item in data.get("response", []):
            score = fixture_match_score(item, home_q, away_q)
            if score > best_score:
                best_score = score
                best_match = item
            if score >= 0.86:
                return item

    if best_match and best_score >= 0.72:
        return best_match
    return find_api_football_match_by_team(home_q, away_q)


def is_major_fixture(item: dict) -> bool:
    league = item.get("league", {})
    league_id = league.get("id")
    league_name = str(league.get("name", "")).lower()
    return league_id in MAJOR_LEAGUE_IDS or any(
        keyword in league_name for keyword in POPULAR_LEAGUE_KEYWORDS
    )


def fixture_popularity_score(item: dict, odds: dict | None = None) -> float:
    score = 0.0
    if odds:
        score += 80
    if is_major_fixture(item):
        score += 70

    fixture_dt = parse_fixture_datetime(item)
    if fixture_dt:
        hours_until = (fixture_dt - datetime.now(SHANGHAI_TZ)).total_seconds() / 3600
        if hours_until >= 0:
            score += max(0, 48 - min(hours_until, 48))

    status = item.get("fixture", {}).get("status", {}).get("short", "")
    if status in {"1H", "HT", "2H", "ET", "P"}:
        score += 25

    return score


def collect_upcoming_fixtures(days: int = 5) -> list[dict]:
    now = datetime.now(SHANGHAI_TZ)
    fixtures = []
    seen_fixtures = set()

    for delta in range(days):
        date_str = (now + timedelta(days=delta)).strftime("%Y-%m-%d")
        data = api_football_get("/fixtures", {"date": date_str, "timezone": "Asia/Shanghai"})
        for item in data.get("response", []):
            fixture = item.get("fixture", {})
            fixture_id = fixture.get("id")
            status = fixture.get("status", {}).get("short", "")
            fixture_dt = parse_fixture_datetime(item)
            if not fixture_id or fixture_id in seen_fixtures or status in FINISHED_STATUSES:
                continue
            if fixture_dt and fixture_dt < now - timedelta(hours=3):
                continue
            seen_fixtures.add(fixture_id)
            fixtures.append(item)

    return fixtures


def format_fixture_time(item: dict) -> str:
    fixture_dt = parse_fixture_datetime(item)
    if fixture_dt:
        return fixture_dt.strftime("%m-%d %H:%M")
    return item.get("fixture", {}).get("date", "")[:16].replace("T", " ")


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

    today = datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")
    data = api_football_get("/fixtures", {"date": today, "timezone": "Asia/Shanghai"})
    all_matches = sorted(
        data.get("response", []), key=lambda item: item.get("fixture", {}).get("date", "")
    )

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


def cmd_popular(chat_id: int):
    """最近热门比赛"""
    send_msg(chat_id, "🔎 正在用 API-Football 筛选最近热门比赛...")

    candidates = sorted(
        collect_upcoming_fixtures(days=5),
        key=lambda item: fixture_popularity_score(item),
        reverse=True,
    )

    if not candidates:
        send_msg(chat_id, "📭 最近几天暂未找到可展示赛事")
        return

    results = []
    for item in candidates[:25]:
        fixture_id = item.get("fixture", {}).get("id")
        odds = get_api_football_match_winner_odds(fixture_id) if fixture_id else None
        if odds or is_major_fixture(item) or len(results) < 8:
            results.append((item, odds))
        if len(results) >= 10:
            break

    results = sorted(
        results,
        key=lambda row: fixture_popularity_score(row[0], row[1]),
        reverse=True,
    )[:10]

    text = "🔥 最近热门比赛（API-Football）\n\n"
    for item, odds in results:
        match_obj = to_match_obj(item, odds)
        league_name = match_obj.get("competition_name") or "Unknown"
        text += f"{format_fixture_time(item)} | {league_name}\n"
        text += f"{match_obj['home_team']} vs {match_obj['away_team']}\n"
        if odds:
            text += (
                f"  赔率 {odds['home']}/{odds['draw']}/{odds['away']} ({odds.get('bookmaker')})\n"
            )
        else:
            text += "  暂无 API-Football 胜平负赔率\n"
        text += f"  分析: /分析 {match_obj['home_team']} vs {match_obj['away_team']}\n\n"

    send_msg(chat_id, text.strip())


def cmd_help(chat_id: int):
    send_msg(
        chat_id,
        """🤖 Football-Quant 机器人

/分析 法国 vs 瑞典   — 单场五步分析
法国 vs 瑞典          — 也可直接发送
/今日                — 今日全部赛事
/热门                — 最近热门比赛
/帮助                — 显示此帮助

💡 直接发比赛名称也可以，如「法国 vs 瑞典」
""",
    )


# ═══════════════════════════════════════════════════
# 主循环 — 长轮询
# ═══════════════════════════════════════════════════


def main():
    import time

    import requests

    if not TELEGRAM_TOKEN:
        print("❌ 未设置 TELEGRAM_BOT_TOKEN")
        sys.exit(1)

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
                elif text.startswith("/热门") or text.startswith("／热门") or text == "热门":
                    try:
                        cmd_popular(chat_id)
                    except Exception as e:
                        send_msg(chat_id, f"❌ {e}")
                elif text.startswith("/帮助") or text.startswith("／帮助") or text == "帮助":
                    cmd_help(chat_id)
                elif text.startswith("/start"):
                    send_msg(
                        chat_id,
                        "👋 Football-Quant 已就绪\n\n发送 /帮助 查看可用命令\n发送 /热门 查看热门比赛",
                    )
                elif split_vs_query(text) and len(text) < 80:
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
