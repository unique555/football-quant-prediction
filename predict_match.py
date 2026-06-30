#!/usr/bin/env python3
"""
单场比赛多时间点预测
用法:  python3 predict_match.py "France vs Sweden"
      python3 predict_match.py "法国 vs 瑞典"
      python3 predict_match.py --id 537416

每次运行保存快照, 多次运行自动对比历史
"""
import sys, os, json, time, glob, argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import requests, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ODDSPAPI_KEY, FOOTBALL_DATA_KEYS
from model.trainer import get_model
from model.national_trainer import get_national_model
from utils import get_match_score

HISTORY_DIR = "/workspace/football-quant-prediction/reports/match_history"
FD_KEY = FOOTBALL_DATA_KEYS[0] if FOOTBALL_DATA_KEYS else ""


# ═══════════════════════════════════════════════════════════
# 1. 搜索比赛
# ═══════════════════════════════════════════════════════════

def find_match(query: str) -> dict:
    """从 football-data.org 搜索比赛 (未来7天 + 最近14天)"""
    headers = {"X-Auth-Token": FD_KEY}
    
    parts = re.split(r'\s+(?:vs|v|VS|V|-)\s+', query)
    if len(parts) < 2:
        parts = query.split(" vs ")
    if len(parts) < 2:
        raise ValueError(f"无法解析比赛名称: {query}, 请用 '主队 vs 客队' 格式")
    
    home_q, away_q = parts[0].strip(), parts[1].strip()
    print(f"🔍 搜索: {home_q} vs {away_q}")
    
    today = datetime.now(timezone.utc)
    date_from = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    date_to = (today + timedelta(days=7)).strftime("%Y-%m-%d")
    
    competitions = ["WC", "EC", "PL", "ELC", "BL1", "SA", "PD", "FL1", "DED", "PPL", "BSA", "CL"]
    
    for comp in competitions:
        try:
            url = f"https://api.football-data.org/v4/matches"
            r = requests.get(f"{url}?dateFrom={date_from}&dateTo={date_to}", headers=headers, timeout=15)
            if r.status_code != 200:
                continue
            for m in r.json().get("matches", []):
                h = (m["homeTeam"].get("name") or "").lower()
                a = (m["awayTeam"].get("name") or "").lower()
                if not h or not a:
                    continue
                if home_q.lower() in h and away_q.lower() in a:
                    sc = get_match_score(m.get("score", {}) or {})
                    comp_info = m.get("competition", {})
                    return {
                        "match_id": m["id"], "home_team": m["homeTeam"]["name"],
                        "away_team": m["awayTeam"]["name"], "date": m["utcDate"],
                        "status": m.get("status", ""), "stage": m.get("stage", ""),
                        "competition": comp_info.get("code", "?"),
                        "competition_name": comp_info.get("name", "?"),
                        "home_score": sc["home"], "away_score": sc["away"],
                    }
            # 如果不是 WC/EC, 只查一次全局 matches 就够了
            break
        except Exception as e:
            pass
    
    raise ValueError(f"未找到比赛: {home_q} vs {away_q} (范围: {date_from}~{date_to})")


# ═══════════════════════════════════════════════════════════
# 2. 拉取赔率
# ═══════════════════════════════════════════════════════════

COMP_TO_TOURNAMENT = {"WC": 16, "EC": 15, "PL": 17, "ELC": 18, "BL1": 35, "SA": 23, "PD": 8, "FL1": 34, "DED": 37, "PPL": None, "BSA": 325, "CL": 7}

def fetch_match_odds(match: dict) -> dict:
    """为单场比赛拉取 Pinnacle 赔率"""
    tid = COMP_TO_TOURNAMENT.get(match["competition"])
    if not tid:
        return {}
    
    try:
        url = f"https://api.oddspapi.io/v4/odds-by-tournaments?bookmaker=pinnacle&tournamentIds={tid}&apiKey={ODDSPAPI_KEY}"
        time.sleep(1)
        r = requests.get(url, timeout=15)
        if r.status_code != 200:
            return {}
        
        # 拉队名映射
        pr = requests.get(f"https://api.oddspapi.io/v4/participants?sportId=10&apiKey={ODDSPAPI_KEY}", timeout=15)
        participants = pr.json() if pr.status_code == 200 else {}
        
        home_lower = match["home_team"].lower()
        away_lower = match["away_team"].lower()
        
        for item in r.json():
            p1 = participants.get(str(item.get("participant1Id", "")), "")
            p2 = participants.get(str(item.get("participant2Id", "")), "")
            if not p1 or not p2:
                continue
            
            if (home_lower in p1.lower() or p1.lower() in home_lower) and \
               (away_lower in p2.lower() or p2.lower() in away_lower):
                bm = item.get("bookmakerOdds", {}).get("pinnacle", {})
                mkt = bm.get("markets", {}).get("101", {}).get("outcomes", {})
                try:
                    return {
                        "home": float(mkt["101"]["players"]["0"]["price"]),
                        "draw": float(mkt["102"]["players"]["0"]["price"]),
                        "away": float(mkt["103"]["players"]["0"]["price"]),
                        "bookmaker": "Pinnacle",
                        "fetched_at": datetime.now(timezone.utc).isoformat(),
                    }
                except:
                    pass
    except:
        pass
    
    return {}


# ═══════════════════════════════════════════════════════════
# 3. 预测引擎
# ═══════════════════════════════════════════════════════════

def run_prediction(match: dict, odds: dict) -> dict:
    """选择模型跑预测 (国家队优先)"""
    comp = match["competition"]
    home, away = match["home_team"], match["away_team"]
    
    # 国家队赛事 → national model
    if comp in ("WC", "EC"):
        model = get_national_model()
        if not model.ratings:
            model.train(start_year=2018, end_year=2026)
        neutral = True
    else:
        model = get_model()
        neutral = False
    
    # 尝试模型预测
    has_data = home in model.ratings and away in model.ratings
    
    if neutral:
        pred = model.predict(home, away, neutral=True)
    else:
        pred = model.predict(home, away)
    
    pred["source"] = "国家队Poisson模型" if comp in ("WC", "EC") else "俱乐部Poisson模型"
    pred["has_team_data"] = has_data
    
    # 如果没有市场赔率, 用模型概率计算公平赔率
    if not odds:
        pred["fair_odds"] = {
            "home": round(1/pred["p_home"], 2) if pred["p_home"] > 0 else 99,
            "draw": round(1/pred["p_draw"], 2) if pred["p_draw"] > 0 else 99,
            "away": round(1/pred["p_away"], 2) if pred["p_away"] > 0 else 99,
        }
    
    return pred


def compute_value(odds: dict, pred: dict) -> list:
    """对比模型 vs Pinnacle, 找价值"""
    if not odds:
        return []
    
    raw = 1/odds["home"] + 1/odds["draw"] + 1/odds["away"]
    bets = []
    for outcome, mk_odds, p_key in [
        ("主胜", odds["home"], "p_home"),
        ("平局", odds["draw"], "p_draw"),
        ("客胜", odds["away"], "p_away"),
    ]:
        mk_prob = (1/mk_odds) / raw
        mo_prob = pred[p_key]
        edge = (mo_prob / mk_prob - 1) if mk_prob > 0 else 0
        bets.append({
            "outcome": outcome,
            "odds": mk_odds,
            "market_prob": round(mk_prob, 3),
            "model_prob": mo_prob,
            "edge": round(edge, 3),
        })
    return bets


# ═══════════════════════════════════════════════════════════
# 4. 时间点快照管理
# ═══════════════════════════════════════════════════════════

def save_snapshot(match_id: int, data: dict):
    os.makedirs(f"{HISTORY_DIR}/{match_id}", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"{HISTORY_DIR}/{match_id}/{ts}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    return path


def load_snapshots(match_id: int) -> list:
    """加载历史快照"""
    folder = f"{HISTORY_DIR}/{match_id}"
    snaps = []
    if os.path.exists(folder):
        for fname in sorted(glob.glob(f"{folder}/*.json")):
            with open(fname) as f:
                snaps.append(json.load(f))
    return snaps


# ═══════════════════════════════════════════════════════════
# 5. MD 报告生成
# ═══════════════════════════════════════════════════════════

def generate_report(match, odds, pred, value_bets, snapshots, kickoff_delta) -> str:
    home, away = match["home_team"], match["away_team"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    lines = [
        f"# ⚽ {home} vs {away} — 单场预测报告",
        f"",
        f"> 生成: {now_str} | 比赛: {match.get('stage','')} | ID: {match['match_id']}",
        f"> 开赛: {match['date'][:16].replace('T',' ')} | 距离开赛: {_format_delta(kickoff_delta)}",
        f"> 状态: {match['status']} | 赛事: {match.get('competition_name','?')}",
        f"",
    ]
    
    # 已有比分
    if match.get("home_score") is not None:
        lines.append(f"### 📊 当前比分: {match['home_team']} {match['home_score']} - {match['away_score']} {match['away_team']}")
        lines.append("")
    
    # 核心预测
    lines.append("## 🎯 核心预测")
    lines.append("")
    lines.append(f"**数据源**: {pred.get('source', '?')}")
    lines.append(f"**球队评分**: {'✅ 两队均有' if pred.get('has_team_data') else '⚠️ 部分缺失'}")
    lines.append("")
    
    lines.append("|  | 主胜 | 平局 | 客胜 |")
    lines.append("|--|------|------|------|")
    
    if odds:
        raw = 1/odds["home"] + 1/odds["draw"] + 1/odds["away"]
        lines.append(f"| Pinnacle 赔率 | {odds['home']} | {odds['draw']} | {odds['away']} |")
        lines.append(f"| 市场概率 | {(1/odds['home']/raw):.1%} | {(1/odds['draw']/raw):.1%} | {(1/odds['away']/raw):.1%} |")
        lines.append(f"| 返还率 | {1/raw:.1%} | | |")
    
    lines.append(f"| **模型概率** | **{pred['p_home']:.1%}** | **{pred['p_draw']:.1%}** | **{pred['p_away']:.1%}** |")
    lines.append("")
    
    if pred.get("home_xg", 0) > 0:
        lines.append(f"🔮 **预测: {pred['prediction']}** ({pred['confidence']:.0%}) | xG: {pred['home_xg']}-{pred['away_xg']}")
    else:
        lines.append(f"🔮 **预测: {pred['prediction']}** ({pred['confidence']:.0%})")
    
    if pred.get("top_scores"):
        scores = " | ".join(f"{s} ({p:.1%})" for s, p in pred["top_scores"][:3])
        lines.append(f"⚽ 最可能比分: {scores}")
    
    # 价值投注
    if value_bets:
        real_v = [v for v in value_bets if v["edge"] > 0.03]
        if real_v:
            lines.append("")
            lines.append("## 💎 价值投注分析")
            lines.append("")
            lines.append("| 方向 | 赔率 | 市场概率 | 模型概率 | 优势 |")
            lines.append("|------|------|----------|----------|------|")
            for v in sorted(real_v, key=lambda x: -x["edge"]):
                mark = "🔥" if v["edge"] > 0.10 else "⭐" if v["edge"] > 0.05 else ""
                lines.append(f"| {v['outcome']} | {v['odds']} | {v['market_prob']:.1%} | {v['model_prob']:.1%} | {mark} +{v['edge']:.1%} |")
    
    # 历史快照对比
    if snapshots:
        lines.append("")
        lines.append("## 📈 时间点对比 (赔率走势)")
        lines.append("")
        lines.append("| 时间 | 距开赛 | 主赔率 | 平赔率 | 客赔率 | 模型预测 | 置信度 |")
        lines.append("|------|--------|--------|--------|--------|----------|--------|")
        
        for s in snapshots:
            ts = s.get("timestamp", "")[:16].replace("T", " ")
            delta = s.get("kickoff_delta_min", 0)
            delta_str = _format_delta(delta)
            o = s.get("odds", {})
            p = s.get("prediction", {})
            
            if o:
                lines.append(f"| {ts} | {delta_str} | {o.get('home','?')} | {o.get('draw','?')} | {o.get('away','?')} | {p.get('prediction','?')} | {p.get('confidence',0):.0%} |")
            else:
                lines.append(f"| {ts} | {delta_str} | — | — | — | {p.get('prediction','?')} | {p.get('confidence',0):.0%} |")
        
        # 走势分析
        if len(snapshots) >= 2 and snapshots[-1].get("odds") and snapshots[0].get("odds"):
            _add_trend_analysis(lines, snapshots)
    
    # 最终结论
    lines.append("")
    lines.append("## 🏁 最终结论")
    lines.append("")
    
    if len(snapshots) >= 3:
        stable = _check_stability(snapshots)
        if stable:
            lines.append(f"- ✅ 赔率走势稳定, 预测可靠性高")
        else:
            lines.append(f"- ⚠️ 赔率波动较大, 注意市场情绪变化")
    
    if pred["confidence"] > 0.55:
        lines.append(f"- 模型置信度较高 ({pred['confidence']:.0%}), 预测方向可靠")
    elif pred["confidence"] > 0.40:
        lines.append(f"- 模型置信度中等 ({pred['confidence']:.0%}), 比赛较为均势")
    else:
        lines.append(f"- 模型置信度偏低 ({pred['confidence']:.0%}), 比赛高度不确定")
    
    if value_bets:
        best_value = max(value_bets, key=lambda x: x["edge"])
        if best_value["edge"] > 0.05:
            lines.append(f"- 💡 市场可能低估了 **{best_value['outcome']}** (优势 +{best_value['edge']:.1%})")
    
    lines.append("")
    lines.append("---")
    lines.append(f"> 🤖 自动生成 | 下次运行 `python3 predict_match.py \"{home} vs {away}\"` 可追加新时间点")
    
    return "\n".join(lines)


def _format_delta(minutes: float) -> str:
    if minutes is None:
        return "?"
    if minutes < 0:
        return f"开赛后{-int(minutes)}分钟"
    if minutes < 60:
        return f"赛前{int(minutes)}分钟"
    if minutes < 1440:
        return f"赛前{int(minutes/60)}小时"
    return f"赛前{int(minutes/1440)}天{int(minutes%1440/60)}小时"


def _check_stability(snapshots: list) -> bool:
    """检查赔率是否稳定"""
    if len(snapshots) < 2:
        return True
    first = snapshots[0].get("odds", {})
    last = snapshots[-1].get("odds", {})
    if not first or not last:
        return True
    home_move = abs(last.get("home", 2) - first.get("home", 2)) / first.get("home", 2)
    return home_move < 0.08


def _add_trend_analysis(lines: list, snapshots: list):
    """赔率走势文字分析"""
    lines.append("")
    lines.append("### 📊 走势分析")
    
    first = snapshots[0]
    last = snapshots[-1]
    o1 = first.get("odds", {})
    o2 = last.get("odds", {})
    
    if o1 and o2:
        h_move = (o2["home"] - o1["home"]) / o1["home"]
        d_move = (o2["draw"] - o1["draw"]) / o1["draw"]
        a_move = (o2["away"] - o1["away"]) / o1["away"]
        
        lines.append(f"- 主胜赔率: {o1['home']} → {o2['home']} ({h_move:+.1%})")
        lines.append(f"- 平局赔率: {o1['draw']} → {o2['draw']} ({d_move:+.1%})")
        lines.append(f"- 客胜赔率: {o1['away']} → {o2['away']} ({a_move:+.1%})")
        
        # 判断资金流向
        if h_move < -0.03:
            lines.append("- 📈 资金流向主胜, 市场看好主队")
        elif a_move < -0.03:
            lines.append("- 📈 资金流向客胜, 市场看好客队")
        elif abs(h_move) < 0.02:
            lines.append("- ➡️ 赔率基本稳定, 市场无明确方向")
        else:
            lines.append("- 📊 赔率波动, 建议关注临场变化")


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="单场比赛多时间点预测")
    parser.add_argument("query", nargs="?", help="比赛名称, 如 'France vs Sweden'")
    parser.add_argument("--id", type=int, help="按 match_id 查询")
    args = parser.parse_args()
    
    if not args.query and not args.id:
        parser.error("请提供比赛名称或 --id")
    
    # 1. 查找比赛
    if args.id:
        # 按 ID 查找
        headers = {"X-Auth-Token": FD_KEY}
        r = requests.get(f"https://api.football-data.org/v4/matches/{args.id}", headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"❌ 未找到 match_id={args.id}")
            return
        m = r.json()
        sc = get_match_score(m.get("score", {}) or {})
        match = {
            "match_id": m["id"], "home_team": m["homeTeam"]["name"],
            "away_team": m["awayTeam"]["name"], "date": m["utcDate"],
            "status": m.get("status", ""), "stage": m.get("stage", ""),
            "competition": m.get("competition", {}).get("code", "?"),
            "competition_name": m.get("competition", {}).get("name", "?"),
            "home_score": sc["home"], "away_score": sc["away"],
        }
    else:
        match = find_match(args.query)
    
    home, away = match["home_team"], match["away_team"]
    print(f"\n✅ 找到: {home} vs {away}")
    print(f"   ID: {match['match_id']} | {match['competition_name']} | {match['status']}")
    print(f"   时间: {match['date'][:16].replace('T',' ')}")
    
    # 2. 计算距离开赛时间
    kickoff = datetime.fromisoformat(match["date"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    kickoff_delta = (kickoff - now).total_seconds() / 60  # 分钟, 负值=已开赛
    print(f"   距离开赛: {_format_delta(kickoff_delta)}")
    
    # 3. 拉赔率
    print(f"\n📡 拉取 Pinnacle 赔率...")
    odds = fetch_match_odds(match)
    if odds:
        print(f"   ✅ {odds['home']}/{odds['draw']}/{odds['away']}")
    else:
        print(f"   ⚠️ 无赔率数据 (该联赛可能无 Pinnacle 覆盖)")
    
    # 4. 跑预测
    print(f"\n🔮 运行预测模型...")
    pred = run_prediction(match, odds)
    print(f"   {pred['source']} → {pred['prediction']} ({pred['confidence']:.0%})")
    if pred.get("home_xg", 0) > 0:
        print(f"   xG: {pred['home_xg']}-{pred['away_xg']}")
    
    # 5. 价值分析
    value_bets = compute_value(odds, pred) if odds else []
    if value_bets:
        real_v = [v for v in value_bets if v["edge"] > 0.03]
        if real_v:
            print(f"\n💎 价值发现:")
            for v in sorted(real_v, key=lambda x: -x["edge"]):
                print(f"   {v['outcome']} @ {v['odds']} | 模型 {v['model_prob']:.1%} vs 市场 {v['market_prob']:.1%} | +{v['edge']:.1%}")
    
    # 6. 保存快照
    snapshot_data = {
        "timestamp": now.isoformat(),
        "match": match,
        "odds": odds or None,
        "prediction": pred,
        "value_bets": value_bets,
        "kickoff_delta_min": round(kickoff_delta, 1),
    }
    snap_path = save_snapshot(match["match_id"], snapshot_data)
    print(f"\n💾 快照已保存: {snap_path}")
    
    # 7. 加载历史
    snapshots = load_snapshots(match["match_id"])
    if len(snapshots) > 1:
        print(f"📂 历史快照: {len(snapshots)} 次 (首次: {snapshots[0]['timestamp'][:16]})")
    else:
        print(f"📂 这是首次预测, 再次运行可追加新时间点")
    
    # 8. 生成报告
    report = generate_report(match, odds, pred, value_bets, snapshots, kickoff_delta)
    report_path = f"/workspace/football-quant-prediction/reports/match_{match['match_id']}_{now.strftime('%Y%m%d_%H%M%S')}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"\n📄 报告: {report_path}")
    print()
    print("=" * 60)
    print(f"  ✅ 完成! 下次赛前再跑: python3 predict_match.py \"{home} vs {away}\"")
    print("=" * 60)


if __name__ == "__main__":
    main()
