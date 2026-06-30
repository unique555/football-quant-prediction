"""
ML 模型训练: 独立概率估计

用历史数据训练 LightGBM，输出与市场赔率「独立」的预测概率
这个概率是五步管道 Step 4 定价检测的关键输入
"""
import pandas as pd
import numpy as np
import pickle
import warnings
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score, log_loss, brier_score_loss
from sklearn.preprocessing import StandardScaler
import lightgbm as lgb

warnings.filterwarnings('ignore')


def load_training_data() -> pd.DataFrame:
    df = pd.read_csv('/workspace/football-quant-prediction/data/training_set.csv')
    df['match_id'] = range(len(df))
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """构建增强特征矩阵（不含赔率 → 独立于市场）"""
    X = pd.DataFrame()

    # ---- ELO ----
    X['elo_home'] = df['elo_home']
    X['elo_away'] = df['elo_away']
    X['elo_gap'] = df['elo_gap']
    X['elo_gap_abs'] = df['elo_gap'].abs()

    # ---- 近期状态 ----
    X['home_gf_last5'] = df['home_gf_last5']
    X['home_ga_last5'] = df['home_ga_last5']
    X['away_gf_last5'] = df['away_gf_last5']
    X['away_ga_last5'] = df['away_ga_last5']
    X['home_pts_last5'] = df['home_pts_last5']
    X['away_pts_last5'] = df['away_pts_last5']

    # ---- 交叉特征 ----
    X['gf_diff'] = df['home_gf_last5'] - df['away_ga_last5']
    X['ga_diff'] = df['home_ga_last5'] - df['away_gf_last5']
    X['form_diff'] = df['home_pts_last5'] - df['away_pts_last5']

    # ---- ELO × 状态交互 ----
    X['elo_times_form'] = df['elo_gap'] * (df['home_pts_last5'] - df['away_pts_last5'])
    X['elo_times_gf'] = df['elo_gap'] * df['home_gf_last5']

    # ---- 标准化 ----
    scaler = StandardScaler()
    feature_names = X.columns.tolist()
    X_scaled = scaler.fit_transform(X)
    X = pd.DataFrame(X_scaled, columns=feature_names)

    return X, scaler


def train_model(df: pd.DataFrame):
    """训练 LightGBM 多分类模型"""
    print("=" * 60)
    print("  🧠 训练独立概率估计模型 (LightGBM)")
    print("=" * 60)
    print()

    # 按时间分割: 2014-2021 训练, 2022-2024 测试
    train_mask = df['season'] <= 2021
    test_mask = df['season'] >= 2022

    df_train = df[train_mask].copy()
    df_test = df[test_mask].copy()

    print(f"训练集: {len(df_train)} 场 (2014-2021)")
    print(f"测试集: {len(df_test)} 场 (2022-2024)")
    print()

    # 特征
    X_train, scaler = build_features(df_train)
    X_test, _ = build_features(df_test)

    # 标签
    outcome_map = {'home': 0, 'draw': 1, 'away': 2}
    y_train = df_train['outcome'].map(outcome_map)
    y_test = df_test['outcome'].map(outcome_map)

    # 类别权重 (平衡三类)
    counts = y_train.value_counts().sort_index()
    class_weights = {i: len(y_train) / (3 * c) for i, c in counts.items()}

    # 训练
    model = lgb.LGBMClassifier(
        n_estimators=300,
        learning_rate=0.03,
        max_depth=6,
        num_leaves=31,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        class_weight=class_weights,
        random_state=42,
        verbose=-1,
    )

    model.fit(X_train, y_train)

    # ---- 评估 ----
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)

    acc = accuracy_score(y_test, y_pred)
    logloss = log_loss(y_test, y_proba)
    brier = brier_score_loss(
        pd.get_dummies(y_test).values.flatten(),
        y_proba.flatten(),
    )

    print(f"测试集准确率: {acc:.1%}")
    print(f"Log Loss:       {logloss:.4f}")
    print(f"Brier Score:    {brier:.4f}")
    print()

    # 随机基线
    print(f"随机基线准确率: {1/3:.1%}")
    print(f"模型超出基线:   {acc - 1/3:+.1%}")
    print()

    # ---- 特征重要性 ----
    importance = pd.DataFrame({
        'feature': X_train.columns,
        'importance': model.feature_importances_,
    }).sort_values('importance', ascending=False)
    print("特征重要性 TOP 10:")
    for _, row in importance.head(10).iterrows():
        print(f"  {row['feature']:<25s} {row['importance']:.4f}")
    print()

    # ---- 校准分析 ----
    # 预测概率 vs 实际频率
    print("概率校准 (预测概率 → 实际频率):")
    for i, label in enumerate(['Home', 'Draw', 'Away']):
        prob_bins = pd.cut(y_proba[:, i], bins=5)
        grouped = pd.DataFrame({
            'prob_bin': prob_bins,
            'actual': (y_test == i).astype(int),
        }).groupby('prob_bin', observed=False)['actual'].agg(['mean', 'count'])
        print(f"  {label}:")

        for bin_name, row in grouped.iterrows():
            if row['count'] > 5:
                print(f"    {bin_name}: pred≈{bin_name.mid:.2f} → actual={row['mean']:.2%} (n={int(row['count'])})")
    print()

    return model, scaler, outcome_map, {
        'accuracy': acc,
        'log_loss': logloss,
        'brier': brier,
        'importance': importance,
        'y_test': y_test,
        'y_proba': y_proba,
        'df_test': df_test,
    }


def save_model(model, scaler, outcome_map):
    """保存模型"""
    import joblib
    os.makedirs('/workspace/football-quant-prediction/models_store', exist_ok=True)

    joblib.dump(model, '/workspace/football-quant-prediction/models_store/lgb_model.joblib')
    joblib.dump(scaler, '/workspace/football-quant-prediction/models_store/scaler.joblib')
    with open('/workspace/football-quant-prediction/models_store/outcome_map.pkl', 'wb') as f:
        pickle.dump(outcome_map, f)
    print("✅ Model saved to models_store/")


def predict_proba(model, scaler, outcome_map, row: dict) -> tuple[float, float, float]:
    """单行预测 → (home_prob, draw_prob, away_prob)"""
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


import os

if __name__ == "__main__":
    df = load_training_data()
    model, scaler, outcome_map, metrics = train_model(df)
    save_model(model, scaler, outcome_map)
