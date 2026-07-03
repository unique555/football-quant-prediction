"""
报告格式化器 — 把 11 维度分析数据组装为 Telegram 精简版 + 完整报告版

输入：各分析器的返回值 dict
输出：telegram_message (str), full_report (str), raw_json (dict)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def format_reports(
    match_data: dict[str, Any],
    classification: dict[str, Any],
    fundamental: dict[str, Any],
    tactical: dict[str, Any],
    motivation: dict[str, Any],
    odds_data: dict[str, Any],
    goals: dict[str, Any],
    corners: dict[str, Any],
    htft: dict[str, Any],
    verdict: dict[str, Any],
    risks: list[str],
    data_quality_data: dict[str, Any],
) -> dict[str, Any]:
    """
    组装完整报告。

    Returns:
        {
            "telegram_message": str,   # Telegram 精简版
            "full_report": str,        # 完整 Markdown 报告
            "raw_json": dict,          # 原始数据（入库用）
        }
    """
    raw_json = {
        "match": match_data,
        "classification": classification,
        "fundamental": fundamental,
        "tactical": tactical,
        "motivation": motivation,
        "odds": odds_data,
        "goals": goals,
        "corners": corners,
        "htft": htft,
        "verdict": verdict,
        "risks": risks,
        "data_quality": data_quality_data,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    telegram_msg = _format_telegram(
        match_data, classification, fundamental, motivation,
        odds_data, goals, corners, htft, verdict, risks,
    )
    full_report = _format_full(raw_json)

    return {
        "telegram_message": telegram_msg,
        "full_report": full_report,
        "raw_json": raw_json,
    }


# ============================================================
# Telegram 精简版
# ============================================================

def _format_telegram(
    match_data, classification, fundamental, motivation,
    odds_data, goals, corners, htft, verdict, risks,
) -> str:
    lines = ["═" * 30]

    # 标题
    league_name = match_data.get("league_name", "")
    round_name = match_data.get("round_name", "")
    home = match_data.get("home_team", "")
    away = match_data.get("away_team", "")
    kickoff = match_data.get("kickoff_str", "")
    venue = match_data.get("venue", "")
    lines.append(f"⚽ {league_name} {round_name} | {home} vs {away}")
    lines.append(f"⏰ {kickoff}")
    if venue:
        lines.append(f"🏟️ {venue}")
    lines.append("═" * 30)
    lines.append("")

    # 比赛定性
    lines.append("📋 比赛定性")
    cls = classification or {}
    lines.append(f"  类型: {cls.get('match_type', '?')} | 阶段: {cls.get('phase', '?')}")
    mot = motivation or {}
    home_mot = mot.get("motivation", {}).get("home", {})
    away_mot = mot.get("motivation", {}).get("away", {})
    if home_mot or away_mot:
        lines.append(f"  战意: {home} {home_mot.get('level', '?')} | {away} {away_mot.get('level', '?')}")
    lines.append("")

    # 基本面速览
    lines.append("📊 基本面速览")
    fund = fundamental or {}
    home_stand = fund.get("standings", {}).get("home", {})
    away_stand = fund.get("standings", {}).get("away", {})
    home_form = fund.get("form", {}).get("home", {})
    away_form = fund.get("form", {}).get("away", {})
    if home_stand:
        lines.append(f"  {home}  #{home_stand.get('rank', '?')}  近5场: {_short_form(home_form.get('form', ''))}  主场: {home_stand.get('home_record', '?')}")
    if away_stand:
        lines.append(f"  {away}  #{away_stand.get('rank', '?')}  近5场: {_short_form(away_form.get('form', ''))}  客场: {away_stand.get('away_record', '?')}")
    h2h = fund.get("h2h_summary", {})
    if h2h:
        lines.append(f"  交锋(近6): {home} {h2h.get('home_wins', 0)}胜{h2h.get('draws', 0)}平{h2h.get('away_wins', 0)}负")
    lines.append("")

    # 胜平负预测
    v = verdict or {}
    lines.append("🎯 胜平负预测")
    probs = v.get("final_probs", {})
    market_probs = v.get("market_probs", {})
    if probs:
        lines.append(f"  模型概率: 主胜 {probs.get('home', 0):.0%} | 平 {probs.get('draw', 0):.0%} | 客胜 {probs.get('away', 0):.0%}")
    if market_probs:
        lines.append(f"  市场概率: 主胜 {market_probs.get('home', 0):.0%} | 平 {market_probs.get('draw', 0):.0%} | 客胜 {market_probs.get('away', 0):.0%}")
    edge = v.get("best_edge")
    if edge is not None:
        lines.append(f"  → Edge: {v.get('recommendation', '?')} +{edge:.1%} ✅" if edge > 0 else f"  → Edge: {v.get('recommendation', '?')} {edge:.1%}")
    best_odds = v.get("best_odds")
    best_bm = v.get("best_bookmaker", "")
    if best_odds:
        lines.append(f"  推荐赔率: {best_odds} ({best_bm})")
    lines.append("")

    # 盘口分析
    odds = odds_data or {}
    lines.append("💰 盘口分析")
    ah = odds.get("asian_handicap", {})
    if ah:
        lines.append(f"  亚盘: {ah.get('handicap', '?')} ({ah.get('initial', '?')})  水位: 主{ah.get('home_water', '?')}/客{ah.get('away_water', '?')}")
        if ah.get("trend"):
            lines.append(f"  趋势: {ah['trend']}")
    lines.append("")

    # 进球市场
    lines.append("⚽ 进球市场")
    g = goals or {}
    ou = g.get("over_under", {})
    if ou:
        lines.append(f"  大小球: {ou.get('line', '?')}  大球{ou.get('over_odds', '?')} / 小球{ou.get('under_odds', '?')}")
    if g.get("expected_total_goals"):
        lines.append(f"  预测总进球: {g['expected_total_goals']:.1f}球 → 倾向{'大球' if g.get('expected_total_goals', 0) > (ou.get('line', 2.5)) else '小球'}")
    btts = g.get("btts", {})
    if btts:
        lines.append(f"  BTTS: 是{btts.get('yes_odds', '?')} / 否{btts.get('no_odds', '?')}")
    lines.append("")

    # 角球
    lines.append("🚩 角球")
    c = corners or {}
    if c.get("line"):
        lines.append(f"  预测: {c['line']}  大角{c.get('over_odds', '?')} / 小角{c.get('under_odds', '?')}")
        edge_c = c.get("edge")
        if edge_c is not None:
            lines.append(f"  倾向: {'大角' if edge_c > 0 else '小角'} {edge_c:+.1%}")
    else:
        lines.append("  无角球盘口数据")
    lines.append("")

    # 半全场
    lines.append("⏱️ 半全场")
    h = htft or {}
    htft_probs = h.get("htft_probs", {})
    if htft_probs:
        hh = htft_probs.get("HH", 0)
        hd = htft_probs.get("HD", 0)
        dh = htft_probs.get("DH", 0)
        lines.append(f"  主/主: {hh:.0%} | 主/平: {hd:.0%} | 平/主: {dh:.0%}")
        best = h.get("best_combo", "")
        if best:
            lines.append(f"  → 最可能: {_htft_label(best)}")
    lines.append("")

    # 价值投注建议
    lines.append("═" * 30)
    lines.append("💎 价值投注建议")
    if v.get("recommendation"):
        lines.append(f"  推荐: {v['recommendation']} @ {v.get('best_odds', '?')} ({best_bm})")
        ev = v.get("best_ev")
        kelly = v.get("kelly")
        if ev is not None:
            lines.append(f"  Edge: {v.get('best_edge', 0):+.1%} | EV: {ev:+.1%}")
        if kelly is not None:
            lines.append(f"  Kelly: {kelly:.1%}资金 ({v.get('kelly_label', '?')})")
        lines.append(f"  风险: {v.get('risk', '?')} | 信号强度: {v.get('signal_score', '?')}/100")
        lines.append("")
        lines.append("  综合信号:")
        seen_sigs = set()
        for sig in v.get("signals", []):
            if sig not in seen_sigs:
                lines.append(f"  {sig}")
                seen_sigs.add(sig)
        seen_risks = set()
        for r in risks[:3]:
            if r not in seen_risks:
                lines.append(f"  ⚠️ {r}")
                seen_risks.add(r)
    else:
        lines.append("  本场无明显价值方向，建议观望")
    lines.append("═" * 30)

    return "\n".join(lines)


# ============================================================
# 完整报告版
# ============================================================

def _format_full(raw: dict[str, Any]) -> str:
    """生成完整 Markdown 报告"""
    match = raw.get("match", {})
    lines = [
        f"# ⚽ {match.get('home_team', '?')} vs {match.get('away_team', '?')} — 综合分析报告",
        "",
        f"**联赛**: {match.get('league_name', '?')} | **轮次**: {match.get('round_name', '?')}",
        f"**开赛**: {match.get('kickoff_str', '?')}",
        f"**场地**: {match.get('venue', '?')}",
        f"**数据截止**: {raw.get('generated_at', '?')[:16]}",
        "",
        "---",
        "",
    ]

    # 1. 比赛定性
    cls = raw.get("classification", {})
    lines.append("## 1. 📋 比赛定性")
    lines.append("")
    lines.append("| 维度 | 判断 | 依据 |")
    lines.append("|------|------|------|")
    lines.append(f"| 比赛类型 | {cls.get('match_type', '?')} | {cls.get('reason', '')} |")
    lines.append(f"| 强势方 | {cls.get('favorite', '?')} | {cls.get('favorite_reason', '')} |")
    lines.append(f"| 赛事阶段 | {cls.get('phase', '?')} | {cls.get('phase_reason', '')} |")
    lines.append(f"| 德比 | {cls.get('is_derby', '?')} | — |")
    lines.append("")

    # 2. 基本面
    fund = raw.get("fundamental", {})
    lines.append("## 2. 📊 基本面")
    lines.append("")
    standings = fund.get("standings", {})
    if standings:
        lines.append("### 2.1 联赛排名")
        lines.append("")
        lines.append("| | 排名 | 积分 | 已赛 | 胜 | 平 | 负 | 进 | 失 | 净 | 近5场 |")
        lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for side in ["home", "away"]:
            s = standings.get(side, {})
            if s:
                lines.append(f"| {match.get(side+'_team','?')} | #{s.get('rank','?')} | {s.get('points','?')} | {s.get('played','?')} | {s.get('win','?')} | {s.get('draw','?')} | {s.get('lose','?')} | {s.get('goals_for','?')} | {s.get('goals_against','?')} | {s.get('goal_diff','?')} | {s.get('form','?')} |")
        lines.append("")

    form = fund.get("form", {})
    if form:
        lines.append("### 2.2 近期状态 (近10场)")
        lines.append("")
        lines.append("| | 胜 | 平 | 负 | 进球均 | 失球均 | 零封率 | 状态分 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for side in ["home", "away"]:
            f = form.get(side, {})
            if f:
                lines.append(f"| {match.get(side+'_team','?')} | {f.get('wins','?')} | {f.get('draws','?')} | {f.get('losses','?')} | {f.get('goals_for_avg','?')} | {f.get('goals_against_avg','?')} | {f.get('clean_sheet_rate','?')} | {f.get('form_score','?')} |")
        lines.append("")

    h2h = fund.get("h2h", [])
    h2h_sum = fund.get("h2h_summary", {})
    if h2h:
        lines.append("### 2.3 历史交锋")
        lines.append("")
        lines.append("| 日期 | 赛事 | 主队 | 比分 | 客队 |")
        lines.append("|---|---|---|---|---|")
        for m in h2h:
            lines.append(f"| {m.get('date','?')[:10]} | {m.get('league','?')} | {m.get('home_team','?')} | {m.get('home_goals','?')}-{m.get('away_goals','?')} | {m.get('away_team','?')} |")
        lines.append(f"| **汇总** | | | | **{match.get('home_team','')} {h2h_sum.get('home_wins',0)}胜{h2h_sum.get('draws',0)}平{h2h_sum.get('away_wins',0)}负** |")
        lines.append("")

    # 3-11 用简化格式（完整数据在 raw_json 中）
    for section, title, emoji in [
        ("tactical", "战术分析", "🎯"),
        ("motivation", "战意与剧本", "🔥"),
        ("odds", "盘口分析", "💰"),
        ("goals", "进球市场", "⚽"),
        ("corners", "角球分析", "🚩"),
        ("htft", "半全场分析", "⏱️"),
    ]:
        data = raw.get(section, {})
        if data:
            lines.append(f"## {_section_num(section)}. {emoji} {title}")
            lines.append("")
            lines.append("```json")
            lines.append(str(data)[:2000])  # 截断过长的数据
            lines.append("```")
            lines.append("")

    # 9. 胜平负判定
    v = raw.get("verdict", {})
    lines.append("## 9. 🎯 胜平负综合判定")
    lines.append("")
    probs = v.get("final_probs", {})
    if probs:
        lines.append("| | 主胜 | 平局 | 客胜 |")
        lines.append("|---|---|---|---|")
        lines.append(f"| 最终概率 | {probs.get('home',0):.1%} | {probs.get('draw',0):.1%} | {probs.get('away',0):.1%} |")
        lines.append("")
    if v.get("recommendation"):
        lines.append(f"**推荐**: {v['recommendation']} @ {v.get('best_odds','?')}")
        lines.append(f"**Edge**: {v.get('best_edge', 0):+.1%} | **EV**: {v.get('best_ev', 0):+.1%} | **Kelly**: {v.get('kelly', 0):.1%}")
    lines.append("")

    # 10. 风险提示
    risks = raw.get("risks", [])
    if risks:
        lines.append("## 10. ⚠️ 风险提示")
        lines.append("")
        for r in risks:
            lines.append(f"- {r}")
        lines.append("")

    # 11. 数据质量
    dq = raw.get("data_quality", {})
    lines.append("## 11. 📊 数据质量报告")
    lines.append("")
    checks = dq.get("checks", [])
    if checks:
        lines.append("| 维度 | 状态 | 说明 |")
        lines.append("|---|---|---|")
        for c in checks:
            lines.append(f"| {c.get('dimension','?')} | {c.get('status','?')} | {c.get('detail','?')} |")
        lines.append("")
        lines.append(f"**整体数据质量**: {dq.get('total_score', 0)}/100 → {'可分析' if dq.get('analyzable') else '数据不足'}")
    lines.append("")
    lines.append(f"> 🤖 自动生成于 {raw.get('generated_at', '?')[:16]} | 数据源: API-Football")

    return "\n".join(lines)


# ============================================================
# 工具函数
# ============================================================

def _short_form(form_str: str) -> str:
    """取近5场，如 'WWDLW' → '4胜1平'"""
    if not form_str:
        return "?"
    recent = form_str[:5]
    w = recent.count("W")
    d = recent.count("D")
    l = recent.count("L")
    return f"{w}胜{d}平{l}负"


def _htft_label(combo: str) -> str:
    """HH → 主胜/主胜"""
    labels = {
        "HH": "主胜/主胜", "HD": "主胜/平局", "HA": "主胜/客胜",
        "DH": "平局/主胜", "DD": "平局/平局", "DA": "平局/客胜",
        "AH": "客胜/主胜", "AD": "客胜/平局", "AA": "客胜/客胜",
    }
    return labels.get(combo, combo)


def _section_num(section: str) -> int:
    nums = {
        "tactical": 3, "motivation": 4, "odds": 5,
        "goals": 6, "corners": 7, "htft": 8,
    }
    return nums.get(section, 0)
