#!/usr/bin/env python3
"""
每日运行脚本 — 拉取当前比赛 + 赔率 → 预测 → 输出 MD 报告
用法: python3 run_daily.py
输出: reports/YYYY-MM-DD_predictions.md
"""
import os, sys, json, time
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ODDSPAPI_KEY, FOOTBALL_DATA_KEYS
from model.trainer import get_model
from model.national_trainer import get_national_model
from notify import send

# ============================================================
# 配置
# ============================================================
BASE_URL = "https://api.football-data.org/v4"
REPORTS_DIR = "/workspace/football-quant-prediction/reports"

# 联赛映射: football-data.org code → (中文名, OddsPapi tournament_id)
LEAGUES = {
    "PL":  ("英超", 17),
    "ELC": ("英冠", 18),
    "BL1": ("德甲", 35),
    "SA":  ("意甲", 23),
    "PD":  ("西甲", 8),
    "FL1": ("法甲", 34),
    "DED": ("荷甲", 37),
    "PPL": ("葡超", None),
    "BSA": ("巴甲", 325),
    "CL":  ("欧冠", 7),
    "WC":  ("世界杯", 16),   # 国家队 → NationalTeamRatingModel
    "EC":  ("欧洲杯", None), # 国家队 → NationalTeamRatingModel
}

# 国家队赛事 (用 NationalTeamRatingModel)
NATIONAL_CODES = {"WC", "EC"}


# ============================================================
# 数据拉取
# ============================================================

def fetch_upcoming_matches() -> list[dict]:
    """从 football-data.org 拉取未来 7 天比赛"""
    all_matches = []
    key_idx = 0
    
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    next_week = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    
    for code, (lname, _) in LEAGUES.items():
        key = FOOTBALL_DATA_KEYS[key_idx % len(FOOTBALL_DATA_KEYS)]
        key_idx += 1
        headers = {"X-Auth-Token": key}
        
        try:
            url = f"{BASE_URL}/competitions/{code}/matches"
            params = f"?dateFrom={today}&dateTo={next_week}&status=SCHEDULED"
            time.sleep(0.7)  # 速率控制
            r = requests.get(url + params, headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            
            for m in r.json().get("matches", []):
                all_matches.append({
                    "league_name": lname,
                    "league_code": code,
                    "match_id": m.get("id"),
                    "date": m.get("utcDate", ""),
                    "status": m.get("status", ""),
                    "home_team": m.get("homeTeam", {}).get("name", ""),
                    "away_team": m.get("awayTeam", {}).get("name", ""),
                    "matchday": m.get("matchday"),
                })
        except Exception as e:
            print(f"  ⚠️ {lname} 拉取失败: {e}")
    
    return all_matches


def fetch_live_matches() -> list[dict]:
    """拉取正在进行的比赛"""
    all_matches = []
    key_idx = 0
    
    for code, (lname, _) in LEAGUES.items():
        key = FOOTBALL_DATA_KEYS[key_idx % len(FOOTBALL_DATA_KEYS)]
        key_idx += 1
        headers = {"X-Auth-Token": key}
        
        try:
            url = f"{BASE_URL}/competitions/{code}/matches"
            params = "?status=LIVE"
            time.sleep(0.7)
            r = requests.get(url + params, headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            
            for m in r.json().get("matches", []):
                score = m.get("score", {}).get("fullTime", {})
                all_matches.append({
                    "league_name": lname,
                    "league_code": code,
                    "match_id": m.get("id"),
                    "date": m.get("utcDate", ""),
                    "status": "LIVE",
                    "home_team": m.get("homeTeam", {}).get("name", ""),
                    "away_team": m.get("awayTeam", {}).get("name", ""),
                    "home_goals": score.get("home"),
                    "away_goals": score.get("away"),
                })
        except Exception as e:
            print(f"  ⚠️ {lname} LIVE 拉取失败: {e}")
    
    return all_matches


def fetch_odds(tournament_id: int) -> dict:
    """从 OddsPapi 拉取赔率, 按 fixture_id 索引"""
    if not tournament_id:
        return {}
    
    try:
        url = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds={tournament_id}&apiKey={ODDSPAPI_KEY}"
        time.sleep(1)
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return {}
        
        odds_map = {}
        for item in r.json():
            bm = item.get("bookmakerOdds", {}).get("pinnacle", {})
            mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
            try:
                odds_map[str(item.get("participant1Id"))] = {
                    "home": float(mkt["101"]["players"]["0"]["price"]),
                    "draw": float(mkt["102"]["players"]["0"]["price"]),
                    "away": float(mkt["103"]["players"]["0"]["price"]),
                }
            except (KeyError, TypeError):
                pass
        return odds_map
    except Exception as e:
        print(f"  ⚠️ OddsPapi 拉取失败 (tournament {tournament_id}): {e}")
        return {}


# ============================================================
# 分析引擎
# ============================================================

def find_value(market_odds: dict, model_pred: dict) -> list:
    """对比市场赔率找价值投注"""
    if not market_odds:
        return []
    
    bets = []
    for outcome, mk_odds, mp_key in [
        ("主胜", market_odds.get("home", 99), "p_home"),
        ("平局", market_odds.get("draw", 99), "p_draw"),
        ("客胜", market_odds.get("away", 99), "p_away"),
    ]:
        if mk_odds and mk_odds > 1.01:
            market_prob = 1 / mk_odds
            model_prob = model_pred.get(mp_key, 0)
            edge = (model_prob / market_prob - 1) if market_prob > 0 else 0
            bets.append({
                "outcome": outcome,
                "odds": mk_odds,
                "market_prob": round(market_prob, 3),
                "model_prob": model_prob,
                "edge": round(edge, 3),
            })
    return bets


# ============================================================
# MD 报告生成
# ============================================================

def generate_md(matches: list, live_matches: list, model, 
                today_str: str, retrain_count: int) -> str:
    lines = [
        f"# ⚽ 每日预测报告 — {today_str}",
        "",
        f"> 模型: Poisson × 球队实力评分 | 训练数据: {retrain_count} 队",
        f"> 数据源: football-data.org + OddsPapi (Pinnacle)",
        f"> 联赛: {len(LEAGUES)} 个 | 未来比赛: {len(matches)} 场 | 进行中: {len(live_matches)} 场",
        "",
        "---",
        "",
    ]

    # 进行中比赛
    if live_matches:
        lines.append("## 🔴 进行中的比赛")
        lines.append("")
        for m in live_matches:
            pred = m.get("prediction", {})
            hg = m.get("home_goals", "?")
            ag = m.get("away_goals", "?")
            lines.append(f"**{m['home_team']} {hg}-{ag} {m['away_team']}** ({m['league_name']})")
            lines.append(f"  xG: {pred.get('home_xg','?')}-{pred.get('away_xg','?')} | 模型预测: {pred.get('prediction','?')} ({pred.get('confidence',0):.0%})")
            lines.append("")
        lines.append("")

    # 未来比赛预测
    if matches:
        lines.append("## 📅 未来 7 天比赛预测")
        lines.append("")
        
        by_date = defaultdict(list)
        for m in matches:
            d = m.get("date", "")[:10]
            by_date[d].append(m)
        
        for date_str in sorted(by_date.keys()):
            lines.append(f"### {date_str}")
            lines.append("")
            lines.append("| 时间 | 联赛 | 主队 | 客队 | 预测 | 置信度 | xG | 价值 |")
            lines.append("|------|------|------|------|------|--------|-----|------|")
            
            for m in by_date[date_str]:
                t = m.get("date", "")[11:16] or "--:--"
                pred = m.get("prediction", {})
                values = m.get("value_bets", [])
                value_str = ", ".join(
                    f"{v['outcome']} +{v['edge']:.0%}" 
                    for v in values if v.get("edge", 0) > 0.05
                ) or "—"
                
                lines.append(
                    f"| {t} | {m['league_name']} | {m['home_team']} | {m['away_team']} | "
                    f"**{pred.get('prediction','?')}** | {pred.get('confidence',0):.0%} | "
                    f"{pred.get('home_xg','?')}-{pred.get('away_xg','?')} | {value_str} |"
                )
            lines.append("")
        
        # 详细预测
        lines.append("---")
        lines.append("")
        lines.append("## 📊 详细预测")
        lines.append("")
        
        for m in matches:
            pred = m.get("prediction", {})
            values = m.get("value_bets", [])
            
            lines.append(f"### {m['home_team']} vs {m['away_team']}")
            lines.append(f"**{m['league_name']}** | {m.get('date','')[:16].replace('T',' ')}")
            lines.append("")
            
            lines.append("|  | 主胜 | 平局 | 客胜 |")
            lines.append("|--|------|------|------|")
            
            mk = m.get("market_odds")
            if mk:
                raw = 1/mk["home"] + 1/mk["draw"] + 1/mk["away"]
                lines.append(
                    f"| 市场赔率 | {mk['home']} | {mk['draw']} | {mk['away']} |"
                )
                lines.append(
                    f"| 市场概率 | {(1/mk['home']/raw):.1%} | {(1/mk['draw']/raw):.1%} | {(1/mk['away']/raw):.1%} |"
                )
            
            lines.append(
                f"| **模型概率** | **{pred['p_home']:.1%}** | **{pred['p_draw']:.1%}** | **{pred['p_away']:.1%}** |"
            )
            lines.append("")
            lines.append(f"🔮 预测: **{pred['prediction']}** ({pred['confidence']:.0%}) | xG: {pred['home_xg']}-{pred['away_xg']}")
            
            if pred.get("top_scores"):
                scores_str = " | ".join(f"{s} ({p:.1%})" for s, p in pred["top_scores"])
                lines.append(f"⚽ 最可能比分: {scores_str}")
            
            if values:
                real_value = [v for v in values if v.get("edge", 0) > 0.05]
                if real_value:
                    lines.append("")
                    lines.append("💎 **价值投注:**")
                    for v in real_value:
                        lines.append(f"  - {v['outcome']} @ {v['odds']} (模型概率 {v['model_prob']:.1%}, 优势 +{v['edge']:.1%})")
            
            lines.append("")
            lines.append("---")
            lines.append("")

    # 球队评分 TOP10
    lines.append("## 🏆 球队实力评分 TOP 10")
    lines.append("")
    sorted_teams = sorted(model.ratings.items(), key=lambda x: -x[1]["pts"])[:10]
    lines.append("| 排名 | 球队 | 场次 | 胜/平/负 | 进球 | 失球 | 积分 | 进攻 | 防守 |")
    lines.append("|------|------|------|----------|------|------|------|------|------|")
    for rank, (name, r) in enumerate(sorted_teams, 1):
        lines.append(f"| {rank} | {name} | {r['gp']} | {r['w']}/{r['d']}/{r['l']} | {r['gf']} | {r['ga']} | {r['pts']} | {r['off']:.2f} | {r['def']:.2f} |")
    
    lines.append("")
    lines.append("---")
    lines.append(f"> 🤖 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')} | 主场优势系数: {model.home_advantage}")
    
    return "\n".join(lines)


# ============================================================
# 主流程
# ============================================================

def main():
    today_str = datetime.now().strftime("%Y-%m-%d")
    print("=" * 60)
    print(f"  ⚽ 每日预测系统 — {today_str}")
    print("=" * 60)
    print()

    # 1. 训练模型
    print("🧠 训练球队实力模型...")
    model = get_model()
    if not model.ratings or model.last_trained is None:
        df = pd.read_csv("/workspace/football-quant-prediction/data/football_data_co_uk.csv", low_memory=False)
        count = model.train(df, seasons=[2019, 2020, 2021, 2022, 2023, 2024, 2025])
        print(f"   ✅ 初次训练: {count} 队")
    else:
        print(f"   ✅ 已有模型 ({len(model.ratings)} 队, 训练于 {model.last_trained[:10]})")
    print()

    # 2. 拉取比赛
    print("📡 拉取未来 7 天比赛...")
    matches = fetch_upcoming_matches()
    print(f"   ✅ {len(matches)} 场")
    
    print("📡 拉取进行中比赛...")
    live_matches = fetch_live_matches()
    print(f"   ✅ {len(live_matches)} 场")
    print()

    # 3. 拉取赔率 (按联赛)
    print("📡 拉取 OddsPapi 赔率...")
    odds_cache = {}
    for code, (lname, tid) in LEAGUES.items():
        if tid:
            odds_cache[code] = fetch_odds(tid)
    total_odds = sum(len(v) for v in odds_cache.values())
    print(f"   ✅ {total_odds} 组赔率")
    print()

    # 4. 运行预测
    print("🔮 运行预测...")
    national_model = get_national_model()
    if not national_model.ratings:
        print("   🧠 训练国家队模型...")
        national_model.train(start_year=2018, end_year=2026)
    
    all_selected = matches + live_matches
    
    # ── 拉取 OddsPapi 参与者名映射 (一次性) ──
    participants_map = {}
    try:
        pr = requests.get(f"https://api.oddspapi.io/v4/participants?sportId=10&apiKey={ODDSPAPI_KEY}", timeout=15)
        if pr.status_code == 200:
            participants_map = pr.json()
    except:
        pass
    
    for m in all_selected:
        code = m.get("league_code", "")
        is_national = code in NATIONAL_CODES
        is_live = m.get("status") == "LIVE"
        
        if is_national:
            pred = national_model.predict(m["home_team"], m["away_team"], neutral=True)
            pred["source"] = "国家队Poisson模型"
        else:
            pred = model.predict(m["home_team"], m["away_team"], m.get("league_name", ""))
            pred["source"] = "俱乐部Poisson模型"
        
        if is_live and m.get("home_goals") is not None:
            pred = _adjust_inplay(pred, m["home_goals"], m["away_goals"], m.get("date", ""))
            pred["source"] += "+滚球"
        
        m["prediction"] = pred
        
        market_odds = None
        tid = {v[1]: k for k, v in LEAGUES.items() if v[1]}.get(code)
        if tid and code in odds_cache:
            odds_for_league = odds_cache[code]
            for p1_id, o in odds_for_league.items():
                p1_name = participants_map.get(str(p1_id), "")
                if p1_name and (m["home_team"].lower() in p1_name.lower() or p1_name.lower() in m["home_team"].lower()):
                    market_odds = o
                    break
            if not market_odds and odds_for_league:
                market_odds = list(odds_for_league.values())[0] if odds_for_league else None
        
        m["market_odds"] = market_odds
        m["value_bets"] = []
        if market_odds:
            raw = 1/market_odds["home"] + 1/market_odds["draw"] + 1/market_odds["away"]
            m["payout"] = 1/raw
            for outcome, mk_o, mp_key in [("主胜", market_odds["home"], "p_home"), ("平局", market_odds["draw"], "p_draw"), ("客胜", market_odds["away"], "p_away")]:
                mk_prob = (1/mk_o)/raw
                edge = (pred[mp_key]/mk_prob - 1) if mk_prob > 0 else 0
                if edge > 0.03:
                    m["value_bets"].append({"outcome": outcome, "odds": mk_o, "market_prob": round(mk_prob,3), "model_prob": pred[mp_key], "edge": round(edge,3)})
        
        fair_odds = {
            "home": round(1 / pred["p_home"], 2) if pred["p_home"] > 0 else 99,
            "draw": round(1 / pred["p_draw"], 2) if pred["p_draw"] > 0 else 99,
            "away": round(1 / pred["p_away"], 2) if pred["p_away"] > 0 else 99,
        }
        m["fair_odds"] = fair_odds
    
    pred_count = sum(1 for m in all_selected if m.get("prediction"))
    print(f"   ✅ {pred_count} 场预测完成")
    print()

    # 5. 生成 MD 报告
    print("📝 生成 MD 报告...")
    md = generate_md(matches, live_matches, model, today_str, len(model.ratings))
    
    report_path = f"{REPORTS_DIR}/{today_str}_predictions.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"   ✅ 报告: {report_path}")
    
    # 同时保存预测数据供赛后复盘使用
    pred_data = {
        "date": today_str,
        "matches": [
            {k: str(v) if isinstance(v, (pd.Timestamp,)) else v 
             for k, v in m.items() if k != "prediction"}
            for m in matches
        ],
    }
    pred_json = f"{REPORTS_DIR}/{today_str}_predictions.json"
    with open(pred_json, "w") as f:
        json.dump(pred_data, f, indent=2, ensure_ascii=False, default=str)
    print(f"   ✅ 预测数据: {pred_json}")
    
    # ── 推送通知 ──
    total_preds = len(matches)
    if total_preds > 0:
        send(f"📊 每日预测完成: {total_preds}场比赛 | {today_str}")
    
    print()
    print("=" * 60)
    print(f"  ✅ 完成! {len(matches)} 场未来 + {len(live_matches)} 场进行中")
    print(f"  📄 {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
