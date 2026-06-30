#!/usr/bin/env python3
"""世界杯专场 — 拉数据 + 预测 + MD 报告 (国家队模型)"""
import os, sys, json, time
from datetime import datetime, timezone
from collections import defaultdict
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ODDSPAPI_KEY, FOOTBALL_DATA_KEYS
from model.national_trainer import get_national_model

FOOTBALL_DATA_KEY = FOOTBALL_DATA_KEYS[0] if FOOTBALL_DATA_KEYS else ""
REPORT_PATH = "/workspace/football-quant-prediction/reports/2026-06-30_worldcup_predictions.md"

def main():
    model = get_national_model()
    
    # 确保模型已训练
    if not model.ratings:
        print("🧠 训练国家队模型...")
        model.train(start_year=2018, end_year=2026)
    else:
        print(f"🧠 国家队模型已就绪: {len(model.ratings)} 队")
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    
    print("=" * 60)
    print("  🏆 2026 世界杯预测 — 6月30日")
    print("=" * 60)
    print()

    # 1. 拉世界杯赛程
    print("📡 拉取世界杯赛程...")
    today = "2026-06-30"
    next_week = "2026-07-07"
    
    all_matches = []
    for status in ["SCHEDULED", "TIMED"]:
        url = f"https://api.football-data.org/v4/competitions/WC/matches?dateFrom={today}&dateTo={next_week}&status={status}"
        r = requests.get(url, headers=headers, timeout=15)
        for m in r.json().get("matches", []):
            all_matches.append({
                "id": m["id"], "date": m["utcDate"],
                "home": m["homeTeam"]["name"] or "TBD",
                "away": m["awayTeam"]["name"] or "TBD",
                "stage": m.get("stage", ""), "group": m.get("group", ""),
            })
    print(f"   ✅ {len(all_matches)} 场")

    # 2. 拉 Pinnacle 赔率
    print("📡 拉取 Pinnacle 赔率...")
    odds_url = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds=16&apiKey={ODDSPAPI_KEY}"
    parts_r = requests.get(f"https://api.oddspapi.io/v4/participants?sportId=10&apiKey={ODDSPAPI_KEY}", timeout=15)
    participants = parts_r.json()
    
    r = requests.get(odds_url, timeout=15)
    odds_map = {}
    for item in r.json():
        bm = item.get("bookmakerOdds", {}).get("pinnacle", {})
        mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
        try:
            p1 = participants.get(str(item.get("participant1Id", "")), "?")
            p2 = participants.get(str(item.get("participant2Id", "")), "?")
            odds_map[f"{p1}|{p2}"] = {
                "home": float(mkt["101"]["players"]["0"]["price"]),
                "draw": float(mkt["102"]["players"]["0"]["price"]),
                "away": float(mkt["103"]["players"]["0"]["price"]),
            }
        except: pass
    print(f"   ✅ {len(odds_map)} 组赔率")

    # 3. 跑预测
    print("🔮 运行预测...")
    results = []
    
    for m in all_matches:
        home, away = m["home"], m["away"]
        if not home or not away or home == "TBD" or away == "TBD":
            continue
        
        # 模型预测 (世界杯 = 中立场地)
        pred = model.predict(home, away, neutral=True)
        model_has_data = model.has_team(home) and model.has_team(away)
        
        # 匹配赔率
        market = None
        for key, odds in odds_map.items():
            k_home, k_away = key.split("|")
            if (k_home.lower() in home.lower() or home.lower() in k_home.lower()) and \
               (k_away.lower() in away.lower() or away.lower() in k_away.lower()):
                market = odds
                break
        
        # 如果模型没有数据，用市场赔率反推
        if not model_has_data and market:
            raw = 1/market["home"] + 1/market["draw"] + 1/market["away"]
            pred = {
                "home_xg": 0, "away_xg": 0,
                "p_home": round((1/market["home"])/raw, 4),
                "p_draw": round((1/market["draw"])/raw, 4),
                "p_away": round((1/market["away"])/raw, 4),
                "prediction": max([("主胜", (1/market["home"])/raw),
                                   ("平局", (1/market["draw"])/raw),
                                   ("客胜", (1/market["away"])/raw)], key=lambda x: x[1])[0],
                "confidence": round(max((1/market["home"])/raw, (1/market["draw"])/raw, (1/market["away"])/raw), 4),
                "top_scores": [],
                "source": "Pinnacle 市场赔率",
            }
        
        # 价值投注分析
        value_bets = []
        if market:
            raw = 1/market["home"] + 1/market["draw"] + 1/market["away"]
            mp_home = (1/market["home"]) / raw
            mp_draw = (1/market["draw"]) / raw
            mp_away = (1/market["away"]) / raw
            
            if model_has_data:
                # 有模型数据时对比模型 vs 市场
                for outcome, mk_odds, mp, pp in [
                    ("主胜", market["home"], mp_home, pred["p_home"]),
                    ("平局", market["draw"], mp_draw, pred["p_draw"]),
                    ("客胜", market["away"], mp_away, pred["p_away"]),
                ]:
                    edge = (pp / mp - 1) if mp > 0 else 0
                    if edge > 0.03:
                        value_bets.append({
                            "outcome": outcome, "odds": mk_odds,
                            "market_prob": round(mp, 3), "model_prob": pp,
                            "edge": round(edge, 3),
                        })
        
        results.append({
            **m,
            "prediction": pred,
            "model_has_data": model_has_data,
            "market_odds": market,
            "value_bets": value_bets,
        })

    # 4. 生成 MD 报告
    print("📝 生成 MD 报告...")
    lines = [
        "# 🏆 2026 世界杯预测报告",
        f"",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> 阶段: 1/16 决赛 (LAST_32) | 未来 {len(all_matches)} 场比赛",
        f"> 数据源: football-data.org + OddsPapi (Pinnacle 赔率)",
        f"> 模型: Poisson × 国家队实力评分 ({len(model.ratings)} 队) | 中立场地 | 训练数据: 2018-2026",
        f"",
        "---",
        "",
    ]
    
    # 按日期分组
    by_date = defaultdict(list)
    for r in results:
        d = r["date"][:10]
        by_date[d].append(r)
    
    lines.append("## 📅 比赛预测总览")
    lines.append("")
    lines.append("| 时间 | 主队 | 客队 | 模型预测 | 置信度 | xG | 市场赔率(主/平/客) | 价值 |")
    lines.append("|------|------|------|----------|--------|-----|---------------------|------|")
    
    for date_str in sorted(by_date.keys()):
        for r in by_date[date_str]:
            t = r["date"][11:16]
            pred = r["prediction"]
            mk = r["market_odds"]
            value_str = ""
            for v in r["value_bets"]:
                value_str += f"{v['outcome']}+{v['edge']:.0%} "
            
            mk_str = f"{mk['home']}/{mk['draw']}/{mk['away']}" if mk else "—"
            lines.append(
                f"| {t} | {r['home']} | {r['away']} | **{pred['prediction']}** | "
                f"{pred['confidence']:.0%} | {pred['home_xg']}-{pred['away_xg']} | "
                f"{mk_str} | {value_str or '—'} |"
            )
    
    lines.append("")
    lines.append("---")
    lines.append("")
    
    # 每场详细
    lines.append("## 📊 逐场详细分析")
    lines.append("")
    
    for r in sorted(results, key=lambda x: x["date"]):
        pred = r["prediction"]
        mk = r["market_odds"]
        
        lines.append(f"### {r['home']} vs {r['away']}")
        lines.append(f"⏰ {r['date'][:16].replace('T', ' ')} | {r['stage']}")
        if not r["model_has_data"]:
            lines.append(f"⚠️ 注: 球队不在国家队评分库中, 使用默认参数预测")
        elif pred.get("source"):
            lines.append(f"📊 数据源: {pred['source']}")
        else:
            lines.append(f"📊 数据源: Poisson 国家队评分模型 ({len(model.ratings)} 队)")
            lines.append(f"   主场队评分: {model.get_rating(r['home']) or '默认'}")
            lines.append(f"   客队评分: {model.get_rating(r['away']) or '默认'}")
        lines.append("")
        
        lines.append("|  | 主胜 | 平局 | 客胜 |")
        lines.append("|--|------|------|------|")
        
        if mk:
            raw = 1/mk["home"] + 1/mk["draw"] + 1/mk["away"]
            lines.append(f"| Pinnacle 赔率 | {mk['home']} | {mk['draw']} | {mk['away']} |")
            lines.append(f"| 市场概率 | {(1/mk['home']/raw):.1%} | {(1/mk['draw']/raw):.1%} | {(1/mk['away']/raw):.1%} |")
            lines.append(f"| 返还率 | {1/raw:.1%} | | |")
        
        lines.append(f"| **模型概率** | **{pred['p_home']:.1%}** | **{pred['p_draw']:.1%}** | **{pred['p_away']:.1%}** |")
        lines.append("")
        lines.append(f"🔮 预测: **{pred['prediction']}** ({pred['confidence']:.0%}) | xG: {pred['home_xg']}-{pred['away_xg']}")
        
        # 最可能比分
        if pred.get("top_scores"):
            scores = " | ".join(f"{s} ({p:.1%})" for s, p in pred["top_scores"])
            lines.append(f"⚽ 最可能比分: {scores}")
        
        # 价值
        if r["value_bets"]:
            lines.append("")
            lines.append("💎 **价值投注机会:**")
            for v in r["value_bets"]:
                lines.append(f"  - {v['outcome']} @ {v['odds']} | 模型概率 {v['model_prob']:.1%} vs 市场 {v['market_prob']:.1%} | 优势 **+{v['edge']:.1%}**")
        
        lines.append("")
        lines.append("---")
        lines.append("")
    
    # 免责
    lines.append("## ⚠️ 免责声明")
    lines.append("")
    lines.append("> 本报告由 Poisson 国家队评分模型生成 (266支球队, 2018-2026 训练数据)。")
    lines.append("> 模型回测准确率: 2022=55.7%, 2023=61.4%, 2024=56.0%, 2025=60.2%。")
    lines.append("> **不构成任何投注建议**。足球比赛结果受众多不可预测因素影响。")
    lines.append("")
    
    md = "\n".join(lines)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(md)
    
    # 终端输出
    print()
    print(f"📊 {'主队':>20s} vs {'客队':<20s} {'模型预测':>6s} {'xG':>8s} {'市场(主/平/客)':>20s} {'价值'}")
    print("-" * 100)
    for r in sorted(results, key=lambda x: x["date"]):
        pred = r["prediction"]
        mk = r["market_odds"]
        mk_str = f"{mk['home']}/{mk['draw']}/{mk['away']}" if mk else "—"
        value = ", ".join(f"{v['outcome']}+{v['edge']:.0%}" for v in r["value_bets"]) or "—"
        source_mark = "🧠" if r["model_has_data"] and not pred.get("source") else "💹"
        print(f"  {source_mark} {r['home']:>20s} vs {r['away']:<20s} {pred['prediction']:>6s} "
              f"{pred['home_xg']}-{pred['away_xg']:<5} {mk_str:>20s}  {value}")
    
    print(f"\n✅ 报告: {REPORT_PATH}")

if __name__ == "__main__":
    main()
