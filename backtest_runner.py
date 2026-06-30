"""
回测验证脚本

将 380 场合成赛季数据逐场喂入五步管道，
收集预测 vs 实际结果，输出准确率/ROI/Brier Score/分层分析
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collections import defaultdict
from typing import Optional

from data.synthetic_season import generate_season, SyntheticMatch
from engine.consensus.consensus_analyzer import BookmakerSnapshot
from engine.orchestrator.pipeline import run_full_pipeline, FinalReport, FinalVerdict


# ============================================================
# 适配器: SyntheticMatch → 管道输入
# ============================================================

def match_to_bookmakers(m: SyntheticMatch) -> list[BookmakerSnapshot]:
    """将合成赔率转成管道需要的 BookmakerSnapshot"""
    snaps = []
    for o in m.odds:
        raw = 1/o["home"] + 1/o["draw"] + 1/o["away"]
        snaps.append(BookmakerSnapshot(
            name=o["bookmaker"],
            home_odds=o["home"],
            draw_odds=o["draw"],
            away_odds=o["away"],
            implied_home_prob=(1/o["home"])/raw,
            implied_draw_prob=(1/o["draw"])/raw,
            implied_away_prob=(1/o["away"])/raw,
            payout_rate=1/raw,
        ))
    return snaps


def match_to_pipeline(m: SyntheticMatch) -> FinalReport:
    """单场比赛 → 管道预测

    「市场为基础，TSI为修正」— 量化基金的经典做法:
    1. 市场隐含概率 = base (最准确的基准)
    2. TSI偏离 → 修正 base (找市场可能错判的地方)
    3. 修过的概率 vs 实际赔率 → 真 edge

    不赌「我比市场聪明」，赌「市场偶尔反应过度」。
    """
    bms = match_to_bookmakers(m)

    # ---- 市场隐含概率 (基准) ----
    raw = sum(1/b.home_odds + 1/b.draw_odds + 1/b.away_odds for b in bms) / len(bms)
    mkt_home = sum(1/b.home_odds for b in bms) / len(bms) / raw
    mkt_draw = sum(1/b.draw_odds for b in bms) / len(bms) / raw
    mkt_away = sum(1/b.away_odds for b in bms) / len(bms) / raw

    # ---- TSI 修正 ----
    tsi_gap = m.tsi_home - m.tsi_away
    # TSI 的预测概率 (ELO风格)
    elo_home = 1.0 / (1.0 + 10 ** (-tsi_gap / 400.0))
    correction_strength = 0.12  # 修正力度 (小 → 保守)

    # 如果 TSI 认为主队比市场更强 → 提升主队概率
    tsi_implied_home = elo_home * 0.74 + 0.08   # ELO + 主场优势
    tsi_implied_away = (1 - elo_home) * 0.74

    # 混合: 88% 市场 + 12% TSI
    model_h = mkt_home * (1 - correction_strength) + tsi_implied_home * correction_strength
    model_a = mkt_away * (1 - correction_strength) + tsi_implied_away * correction_strength
    model_d = 1.0 - model_h - model_a

    # 归一化
    total = model_h + model_d + model_a
    model_h = max(0.05, model_h / total)
    model_d = max(0.05, model_d / total)
    model_a = max(0.05, model_a / total)
    total2 = model_h + model_d + model_a
    model_h /= total2; model_d /= total2; model_a /= total2

    # ---- 市场最佳赔率 ----
    best_h = min(b.home_odds for b in bms)
    best_d = min(b.draw_odds for b in bms)
    best_a = min(b.away_odds for b in bms)

    return run_full_pipeline(
        home_team=m.home_team,
        away_team=m.away_team,
        league="epl",
        tsi_home=m.tsi_home,
        tsi_away=m.tsi_away,
        asian_handicap=m.asian_handicap,
        initial_odds=(
            m.odds[0]["home"], m.odds[0]["draw"], m.odds[0]["away"],
        ),
        home_form_score=m.home_form,
        away_form_score=m.away_form,
        league_round=m.league_round,
        total_rounds=38,
        is_derby=m.is_derby,
        bookmaker_snapshots=bms,
        model_home_prob=model_h,
        model_draw_prob=model_d,
        model_away_prob=model_a,
        best_home_odds=best_h,
        best_draw_odds=best_d,
        best_away_odds=best_a,
    )


# ============================================================
# 回测指标
# ============================================================

def run_backtest(matches: list[SyntheticMatch]) -> dict:
    """全量回测"""
    results = []
    correct = 0
    total = 0
    skipped = 0

    # 分层收集
    by_type: dict[str, list[bool]] = defaultdict(list)
    by_consensus: dict[str, list[bool]] = defaultdict(list)
    by_verdict: dict[str, list[bool]] = defaultdict(list)

    # ROI 计算 (模拟按预测方向下注)
    total_stake = 0.0
    total_return = 0.0

    # Brier
    brier_sum = 0.0

    for i, m in enumerate(matches):
        report = match_to_pipeline(m)

        # 数量
        total += 1
        actual = m.actual_outcome

        # 方向正确性
        pred_dir = report.recommended_direction
        is_correct = (pred_dir == actual)
        if is_correct:
            correct += 1

        # 跳过的不计入
        if report.final_verdict == FinalVerdict.SKIP:
            skipped += 1
            continue

        # ROI: 用最佳赔率结算
        bms = match_to_bookmakers(m)
        best_h = min(b.home_odds for b in bms)
        best_d = min(b.draw_odds for b in bms)
        best_a = min(b.away_odds for b in bms)
        odds_map = {"home": best_h, "draw": best_d, "away": best_a}
        if pred_dir and report.position_sizing and report.position_sizing.sizing_label != "skip":
            stake = report.position_sizing.recommended_fraction
            total_stake += stake
            if is_correct:
                total_return += stake * odds_map.get(pred_dir, 1.0)

        # Brier Score
        actual_vec = {"home": (1, 0, 0), "draw": (0, 1, 0), "away": (0, 0, 1)}
        a_h, a_d, a_w = actual_vec[actual]
        bs = (
            (report.final_home_prob - a_h) ** 2
            + (report.final_draw_prob - a_d) ** 2
            + (report.final_away_prob - a_w) ** 2
        ) / 3
        brier_sum += bs

        # 分层
        c = report.classification
        if c:
            by_type[c.match_type.value].append(is_correct)

        con = report.consensus
        if con:
            by_consensus[con.consensus_level.value].append(is_correct)

        by_verdict[report.final_verdict.value].append(is_correct)

        results.append(report)

        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{len(matches)} ({((i+1)/len(matches)*100):.0f}%) | "
                  f"当前准确率: {correct/(total-skipped)*100:.1f}%" if (total-skipped) > 0 else "...")

    # ================================================================
    # 汇总
    # ================================================================
    predicted = total - skipped
    accuracy = correct / predicted if predicted > 0 else 0
    roi = (total_return - total_stake) / total_stake if total_stake > 0 else 0
    brier = brier_sum / total if total > 0 else 999

    # 分层准确率
    type_stats = {}
    for t, vals in sorted(by_type.items()):
        type_stats[t] = {"count": len(vals), "accuracy": sum(vals)/len(vals) if vals else 0}

    consensus_stats = {}
    for lvl, vals in sorted(by_consensus.items()):
        consensus_stats[lvl] = {"count": len(vals), "accuracy": sum(vals)/len(vals) if vals else 0}

    verdict_stats = {}
    for v, vals in sorted(by_verdict.items()):
        verdict_stats[v] = {"count": len(vals), "accuracy": sum(vals)/len(vals) if vals else 0}

    # 方向分布
    dir_counts = defaultdict(int)
    for r in results:
        if r.recommended_direction:
            dir_counts[r.recommended_direction] += 1

    # 矩阵: 预测方向 × 实际结果的胜负平分布
    confusion = defaultdict(lambda: defaultdict(int))
    for r, m in zip(results, matches):
        if r.recommended_direction:
            confusion[r.recommended_direction][m.actual_outcome] += 1

    return {
        "total_matches": total,
        "predicted": predicted,
        "skipped": skipped,
        "accuracy": accuracy,
        "roi": roi,
        "brier_score": brier,
        "by_match_type": type_stats,
        "by_consensus": consensus_stats,
        "by_verdict": verdict_stats,
        "direction_distribution": dict(dir_counts),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "reports": results,
    }


def print_report(stats: dict):
    """打印回测报告"""
    print()
    print("=" * 70)
    print("  ⚽ 五步决策管道 — 回测验证报告")
    print("=" * 70)
    print()
    print(f"  总场次:        {stats['total_matches']}")
    print(f"  有效预测:      {stats['predicted']}")
    print(f"  跳过场次:      {stats['skipped']}")
    print(f"  方向准确率:    {stats['accuracy']:.1%}  ← 核心指标")
    print(f"  模拟 ROI:      {stats['roi']:+.2%}")
    print(f"  Brier Score:   {stats['brier_score']:.4f}  (0=完美, 越接近0越好)")
    print()

    # 分层: 比赛类型
    print("  ┌─ 按比赛类型 ──────────────────────────────")
    for t, s in sorted(stats["by_match_type"].items()):
        bar = "█" * int(s["accuracy"] * 20) + "░" * max(0, 20 - int(s["accuracy"] * 20))
        print(f"  │ {t:<20s}  n={s['count']:>3d}  {s['accuracy']:.1%}  {bar}")
    print("  └────────────────────────────────────────────")
    print()

    # 分层: 共识级别
    print("  ┌─ 按共识级别 ──────────────────────────────")
    for lvl, s in sorted(stats["by_consensus"].items()):
        bar = "█" * int(s["accuracy"] * 20) + "░" * max(0, 20 - int(s["accuracy"] * 20))
        print(f"  │ {lvl:<15s}  n={s['count']:>3d}  {s['accuracy']:.1%}  {bar}")
    print("  └────────────────────────────────────────────")
    print()

    # 分层: 置信度
    print("  ┌─ 按置信度 ────────────────────────────────")
    for v, s in sorted(stats["by_verdict"].items()):
        bar = "█" * int(s["accuracy"] * 20) + "░" * max(0, 20 - int(s["accuracy"] * 20))
        print(f"  │ {v:<20s}  n={s['count']:>3d}  {s['accuracy']:.1%}  {bar}")
    print("  └────────────────────────────────────────────")
    print()

    # 方向分布
    print("  ┌─ 预测方向分布 ────────────────────────────")
    dd = stats["direction_distribution"]
    total_pred = sum(dd.values())
    for d, c in sorted(dd.items(), key=lambda x: -x[1]):
        print(f"  │ {d:<10s}  {c:>3d} 次  ({c/total_pred*100:.0f}%)")
    print("  └────────────────────────────────────────────")
    print()

    # 混淆矩阵
    print("  ┌─ 混淆矩阵 (行=预测, 列=实际) ────────────")
    print(f"  │ {'':<10s} {'home':>6s} {'draw':>6s} {'away':>6s}")
    for pred_dir in ["home", "draw", "away"]:
        row = stats["confusion"].get(pred_dir, {})
        h = row.get("home", 0)
        d = row.get("draw", 0)
        a = row.get("away", 0)
        total_row = h + d + a
        if total_row > 0:
            print(f"  │ {pred_dir:<10s} {h:>4d}({h/total_row*100:.0f}%) "
                  f"{d:>4d}({d/total_row*100:.0f}%) "
                  f"{a:>4d}({a/total_row*100:.0f}%)")
    print("  └────────────────────────────────────────────")
    print()

    # 总结
    print("=" * 70)
    if stats["accuracy"] > 0.40:
        print("  ✅ 方向准确率高于随机 (33%)，管道有效")
    else:
        print("  ⚠️ 方向准确率接近或低于随机，需要优化")
    if stats["roi"] > 0:
        print(f"  ✅ 模拟 ROI 为正 ({stats['roi']:+.2%})")
    else:
        print(f"  ⚠️ 模拟 ROI 为负 ({stats['roi']:+.2%})")
    print("=" * 70)


if __name__ == "__main__":
    print("⚽ 生成合成赛季数据...")
    season = generate_season()
    print(f"✓ 生成 {len(season)} 场比赛")
    print()
    print("🔮 运行五步决策管道回测...")
    stats = run_backtest(season)
    print_report(stats)
