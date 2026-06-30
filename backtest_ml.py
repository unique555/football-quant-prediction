"""
ML 增强回测

用训练好的 LightGBM 模型作为独立概率来源，
接入五步管道 Step 4 定价检测，
验证 ROI 能否转正。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
import joblib
import pickle
from collections import defaultdict

from engine.consensus.consensus_analyzer import BookmakerSnapshot
from engine.orchestrator.pipeline import run_full_pipeline, FinalReport, FinalVerdict
from data.train_ml_model import build_features as ml_build_features


# ============================================================
# 加载模型 + 数据
# ============================================================

def load_assets():
    model = joblib.load('models_store/lgb_model.joblib')
    scaler = joblib.load('models_store/scaler.joblib')
    with open('models_store/outcome_map.pkl', 'rb') as f:
        outcome_map = pickle.load(f)
    df = pd.read_csv('data/training_set.csv')
    return model, scaler, outcome_map, df


def load_test_data(df: pd.DataFrame) -> pd.DataFrame:
    """测试集: 2022-2024 赛季"""
    return df[df['season'] >= 2022].copy().reset_index(drop=True)


def generate_odds_row(row) -> list[BookmakerSnapshot]:
    """ELO → 赔率 → BookmakerSnapshot (10家机构)"""
    elo_gap = row['elo_home'] - row['elo_away']
    p_home = 1.0 / (1.0 + 10 ** (-elo_gap / 400.0))
    p_draw = max(0.08, 0.32 - abs(elo_gap) / 800.0)
    p_away = max(0.05, 1.0 - p_home - p_draw)
    total = p_home + p_draw + p_away
    p_home /= total; p_draw /= total; p_away /= total

    bms = []
    bookmaker_names = [
        "bet365", "pinnacle", "william_hill", "betfair", "betway",
        "1xbet", "unibet", "bwin", "sbobet", "marathon",
    ]
    np.random.seed(int(row['match_id']))  # 确定性噪声

    for name in bookmaker_names:
        margin = np.random.uniform(0.92, 0.96)
        noise_h = np.random.normal(0, 0.015)
        noise_d = np.random.normal(0, 0.01)

        odds_h = max(1.05, (1.0 / (p_home + noise_h)) * (1 / margin))
        odds_d = max(1.05, (1.0 / (p_draw + noise_d)) * (1 / margin))
        odds_a = max(1.05, (1.0 / (max(0.03, 1.0 - (p_home + noise_h) - (p_draw + noise_d)))) * (1 / margin))

        raw = 1/odds_h + 1/odds_d + 1/odds_a
        bms.append(BookmakerSnapshot(
            name=name,
            home_odds=round(odds_h, 2),
            draw_odds=round(odds_d, 2),
            away_odds=round(odds_a, 2),
            implied_home_prob=round((1/odds_h)/raw, 4),
            implied_draw_prob=round((1/odds_d)/raw, 4),
            implied_away_prob=round((1/odds_a)/raw, 4),
            payout_rate=round(1/raw, 4),
        ))
    return bms


# ============================================================
# ML 预测
# ============================================================

def ml_predict(model, scaler, outcome_map, row) -> tuple[float, float, float]:
    """ML 模型独立概率估计"""
    features = pd.DataFrame([{
        'elo_home': row['elo_home'], 'elo_away': row['elo_away'],
        'elo_gap': row['elo_gap'], 'elo_gap_abs': abs(row['elo_gap']),
        'home_gf_last5': row['home_gf_last5'], 'home_ga_last5': row['home_ga_last5'],
        'away_gf_last5': row['away_gf_last5'], 'away_ga_last5': row['away_ga_last5'],
        'home_pts_last5': row['home_pts_last5'], 'away_pts_last5': row['away_pts_last5'],
        'gf_diff': row['home_gf_last5'] - row['away_ga_last5'],
        'ga_diff': row['home_ga_last5'] - row['away_gf_last5'],
        'form_diff': row['home_pts_last5'] - row['away_pts_last5'],
        'elo_times_form': row['elo_gap'] * (row['home_pts_last5'] - row['away_pts_last5']),
        'elo_times_gf': row['elo_gap'] * row['home_gf_last5'],
    }])
    features_scaled = scaler.transform(features)
    proba = model.predict_proba(features_scaled)[0]
    return float(proba[0]), float(proba[1]), float(proba[2])


# ============================================================
# 回测
# ============================================================

def run_ml_backtest(test_df: pd.DataFrame, model, scaler, outcome_map):
    """ML → 五步管道 全量回测"""
    correct, total, skipped = 0, 0, 0
    total_stake, total_return = 0.0, 0.0
    brier_sum = 0.0

    by_type = defaultdict(list)
    by_verdict = defaultdict(list)
    direction_counts = defaultdict(int)

    print(f"Running ML-backtest on {len(test_df)} matches...")
    print()

    for i, (_, row) in enumerate(test_df.iterrows()):
        bms = generate_odds_row(row)
        ml_h, ml_d, ml_a = ml_predict(model, scaler, outcome_map, row)

        best_h = min(b.home_odds for b in bms)
        best_d = min(b.draw_odds for b in bms)
        best_a = min(b.away_odds for b in bms)

        report = run_full_pipeline(
            home_team=row['home'],
            away_team=row['away'],
            league="epl",
            tsi_home=min(100, max(30, row['elo_home'] / 20)),
            tsi_away=min(100, max(30, row['elo_away'] / 20)),
            asian_handicap=_estimate_handicap(bms),
            initial_odds=(bms[0].home_odds, bms[0].draw_odds, bms[0].away_odds),
            home_form_score=min(1, row['home_pts_last5'] / 3.0),
            away_form_score=min(1, row['away_pts_last5'] / 3.0),
            league_round=20, total_rounds=38,
            bookmaker_snapshots=bms,
            model_home_prob=ml_h,       # ← ML 独立估计
            model_draw_prob=ml_d,
            model_away_prob=ml_a,
            best_home_odds=best_h,
            best_draw_odds=best_d,
            best_away_odds=best_a,
        )

        total += 1
        actual = row['outcome']
        pred_dir = report.recommended_direction
        is_correct = (pred_dir == actual)
        if is_correct:
            correct += 1

        if report.final_verdict == FinalVerdict.SKIP:
            skipped += 1
            continue

        # ROI
        odds_map = {"home": best_h, "draw": best_d, "away": best_a}
        if pred_dir and report.position_sizing and report.position_sizing.sizing_label != "skip":
            stake = report.position_sizing.recommended_fraction
            total_stake += stake
            if is_correct:
                total_return += stake * odds_map.get(pred_dir, 1.0)

        # Brier
        av = {"home": (1,0,0), "draw": (0,1,0), "away": (0,0,1)}
        ah, ad, aw = av[actual]
        bs = ((report.final_home_prob - ah)**2 + (report.final_draw_prob - ad)**2 + (report.final_away_prob - aw)**2) / 3
        brier_sum += bs

        # Stats
        direction_counts[pred_dir] = direction_counts.get(pred_dir, 0) + 1
        c = report.classification
        if c: by_type[c.match_type.value].append(is_correct)
        by_verdict[report.final_verdict.value].append(is_correct)

        if (i+1) % 100 == 0:
            acc = correct / (total - skipped) if (total - skipped) > 0 else 0
            print(f"  [{i+1}/{len(test_df)}] acc={acc:.1%}")

    # Stats
    predicted = total - skipped
    accuracy = correct / predicted if predicted > 0 else 0
    roi = (total_return - total_stake) / total_stake if total_stake > 0 else 0
    brier = brier_sum / total

    print()
    print("=" * 60)
    print("  ⚽ ML增强五步管道 — 回测报告")
    print("=" * 60)
    print(f"  测试场次:      {total}")
    print(f"  有效预测:      {predicted}")
    print(f"  跳过:          {skipped}")
    print(f"  方向准确率:    {accuracy:.1%}  ← 核心指标")
    print(f"  模拟 ROI:      {roi:+.2%}  ← 盈利能力")
    print(f"  Brier Score:   {brier:.4f}")
    print()

    print(f"  方向分布: {dict(direction_counts)}")
    print()

    # 按比赛类型
    print("  ┌─ 比赛类型 ────────────────────────────")
    for t, v in sorted(by_type.items()):
        a = sum(v)/len(v) if v else 0
        print(f"  │ {t:<25s} n={len(v):>3d}  {a:.1%}")
    print("  └───────────────────────────────────────")
    print()

    # 按置信度
    print("  ┌─ 置信度 ───────────────────────────────")
    for ver, v in sorted(by_verdict.items()):
        a = sum(v)/len(v) if v else 0
        print(f"  │ {ver:<25s} n={len(v):>3d}  {a:.1%}")
    print("  └───────────────────────────────────────")
    print()

    verdict_order = ['high_confidence', 'moderate', 'low_confidence', 'no_edge']
    accs = {ver: (sum(by_verdict[ver])/len(by_verdict[ver]) if by_verdict[ver] else 0)
            for ver in verdict_order}
    has_h = sum(by_verdict['high_confidence']) if 'high_confidence' in by_verdict else 0
    has_l = sum(by_verdict['low_confidence']) if 'low_confidence' in by_verdict else 0

    if has_h and has_l and accs['high_confidence'] > accs['low_confidence']:
        print(f"  ✅ 高置信度 ({accs['high_confidence']:.1%}) > 低置信度 ({accs['low_confidence']:.1%})")
        print(f"     系统正确识别了高质量信号")
    print()

    if roi > 0:
        print(f"  🎉 ROI 为正 ({roi:+.2%})！模型找到了市场尚未充分定价的信息")
    elif roi > -0.05:
        print(f"  ⚡ ROI 接近盈亏平衡 ({roi:+.2%})，小幅优化可转正")
    else:
        print(f"  ⚠️ ROI 仍为负 ({roi:+.2%})，需更多数据/更好特征")

    return accuracy, roi, brier


def _estimate_handicap(bms: list[BookmakerSnapshot]) -> float:
    """从赔率推断亚盘"""
    rh = 1/sum(b.home_odds for b in bms)*len(bms)
    ra = 1/sum(b.away_odds for b in bms)*len(bms)
    ratio = rh / ra if ra else 1.0
    if ratio < 0.4:   return 2.0
    elif ratio < 0.55: return 1.5
    elif ratio < 0.68: return 1.0
    elif ratio < 0.80: return 0.5
    elif ratio < 0.92: return 0.25
    elif ratio < 1.08: return 0.0
    elif ratio < 1.25: return -0.25
    elif ratio < 1.45: return -0.5
    elif ratio < 1.70: return -0.75
    elif ratio < 2.0:  return -1.0
    else: return -1.5


if __name__ == "__main__":
    print("Loading assets...")
    model, scaler, outcome_map, df = load_assets()
    test_df = load_test_data(df)
    print(f"Test set: {len(test_df)} matches")
    print()

    acc, roi, brier = run_ml_backtest(test_df, model, scaler, outcome_map)
