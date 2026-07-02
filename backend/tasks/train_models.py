"""
模型训练定时任务 — 每周用最新历史重训 Stacking 模型

流程：
  1. 从 API-Football 拉取多个联赛多个赛季的历史比赛
  2. 逐场构建特征 + 标签
  3. 训练 Stacking（LGB + XGB + CatBoost）
  4. 校准 + 评估
  5. 保存 + MLflow 记录
  6. 更新 model_versions 表
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)

# 训练用联赛（热门联赛优先，数据充足）
TRAIN_LEAGUES = [
    {"id": 39, "name": "Premier League", "seasons": [2023, 2024]},
    {"id": 140, "name": "La Liga", "seasons": [2023, 2024]},
    {"id": 135, "name": "Serie A", "seasons": [2023, 2024]},
    {"id": 78, "name": "Bundesliga", "seasons": [2023, 2024]},
    {"id": 61, "name": "Ligue 1", "seasons": [2023, 2024]},
    {"id": 2, "name": "Champions League", "seasons": [2023, 2024]},
]

MIN_TRAINING_SAMPLES = 200


@celery_app.task(name="tasks.train_models.retrain_all")
def retrain_all() -> dict:
    """每周一重训 ML 模型"""
    return asyncio.run(_retrain())


async def _retrain() -> dict:
    """执行完整训练流程"""
    from services.telegram_mvp.api_football import ApiFootballClient
    from services.feature_builder import FeatureBuilder
    from services.ml.trainer import StackingTrainer

    api = ApiFootballClient()
    fb = FeatureBuilder(api=api)

    # 1. 收集训练数据
    logger.info("collecting training data...")
    features_list: list[dict[str, float]] = []
    labels_list: list[int] = []

    for league in TRAIN_LEAGUES:
        for season in league["seasons"]:
            try:
                fixtures = _fetch_season_fixtures(api, league["id"], season)
                logger.info("  %s %s: %d fixtures", league["name"], season, len(fixtures))

                for fixture in fixtures:
                    # 只要已结束的比赛（有结果）
                    if fixture.get("fixture", {}).get("status", {}).get("short") not in {"FT", "AET", "PEN"}:
                        continue

                    target = fb.build_target(fixture)
                    if target is None:
                        continue

                    # 构建特征（用赛季统计数据，不用实时赔率）
                    fundamental = _build_fundamental_for_training(api, fixture, league, season)
                    if not fundamental:
                        continue

                    odds_aggregates = _build_dummy_odds(fixture)
                    features = fb.build(fixture, fundamental, odds_aggregates)
                    features_list.append(features)
                    labels_list.append(target)

            except Exception as e:
                logger.warning("  failed %s %s: %s", league["name"], season, e)

    if len(features_list) < MIN_TRAINING_SAMPLES:
        logger.warning("insufficient training data: %d < %d", len(features_list), MIN_TRAINING_SAMPLES)
        return {"status": "skipped", "reason": f"only {len(features_list)} samples"}

    logger.info("training data collected: %d samples", len(features_list))

    # 2. 构建 DataFrame
    features_df = pd.DataFrame(features_list)
    feature_names = list(features_df.columns)
    labels = np.array(labels_list)

    # 填充 NaN
    features_df = features_df.fillna(0.0)

    # 3. 训练
    trainer = StackingTrainer()
    metrics = trainer.train(features_df, labels, feature_names)

    # 4. 保存
    version_tag = trainer.save()
    features_hash = trainer.features_hash()

    # 5. 更新数据库
    await _update_model_version(version_tag, metrics, features_hash, len(features_list))

    # 6. 重新加载推理器
    from services.ml.predictor import reload_predictor
    reload_predictor()

    logger.info("retrain complete: version=%s metrics=%s", version_tag, metrics)
    return {"status": "success", "version": version_tag, "metrics": metrics, "samples": len(features_list)}


def _fetch_season_fixtures(api, league_id: int, season: int) -> list[dict]:
    """拉取一个联赛一个赛季的所有比赛"""
    all_fixtures = []
    page = 1
    while True:
        data = api.get("/fixtures", {
            "league": league_id,
            "season": season,
            "page": page,
        })
        fixtures = data.get("response", [])
        if not fixtures:
            break
        all_fixtures.extend(fixtures)
        paging = data.get("paging", {})
        if page >= paging.get("total", 1):
            break
        page += 1
    return all_fixtures


def _build_fundamental_for_training(
    api, fixture: dict, league: dict, season: int,
) -> dict[str, Any] | None:
    """
    为训练数据构建基本面信息。
    简化版：只拉 standings，不拉 h2h/teams statistics（节省 API 额度）。
    """
    try:
        league_id = league["id"]
        teams = fixture.get("teams", {})
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")

        # 拉积分榜
        data = api.get("/standings", {"league": league_id, "season": season})
        standings_resp = data.get("response", [])
        if not standings_resp:
            return None

        standings_list = standings_resp[0].get("league", {}).get("standings", [[]])[0]

        # 提取主客队排名
        standings = {}
        for entry in standings_list:
            tid = entry.get("team", {}).get("id")
            if tid == home_id:
                standings["home"] = _parse_standings(entry)
            elif tid == away_id:
                standings["away"] = _parse_standings(entry)

        if "home" not in standings or "away" not in standings:
            return None

        # 简化的近期状态（从 standings 的 form 字段推断）
        form = {}
        for side in ["home", "away"]:
            form_str = standings[side].get("form", "")
            form[side] = _form_from_string(form_str)

        return {
            "standings": standings,
            "form": form,
            "home_record": {},
            "away_record": {},
            "h2h": [],
            "h2h_summary": {"home_wins": 0, "draws": 0, "away_wins": 0},
        }
    except Exception:
        return None


def _parse_standings(entry: dict) -> dict:
    all_stats = entry.get("all", {})
    home_stats = entry.get("home", {})
    away_stats = entry.get("away", {})
    goals = all_stats.get("goals", {})
    return {
        "rank": entry.get("rank", 20),
        "team_name": entry.get("team", {}).get("name", ""),
        "points": entry.get("points", 0),
        "played": all_stats.get("played", 0),
        "win": all_stats.get("win", 0),
        "draw": all_stats.get("draw", 0),
        "lose": all_stats.get("lose", 0),
        "goals_for": goals.get("for", 0) or 0,
        "goals_against": goals.get("against", 0) or 0,
        "goal_diff": (goals.get("for", 0) or 0) - (goals.get("against", 0) or 0),
        "form": entry.get("form", ""),
        "home_record": f"{home_stats.get('win',0)}胜{home_stats.get('draw',0)}平{home_stats.get('lose',0)}负",
        "away_record": f"{away_stats.get('win',0)}胜{away_stats.get('draw',0)}平{away_stats.get('lose',0)}负",
        "home_goals_for": home_stats.get("goals", {}).get("for", 0) or 0,
        "home_goals_against": home_stats.get("goals", {}).get("against", 0) or 0,
        "away_goals_for": away_stats.get("goals", {}).get("for", 0) or 0,
        "away_goals_against": away_stats.get("goals", {}).get("against", 0) or 0,
    }


def _form_from_string(form_str: str) -> dict:
    """从 WWDWL 字符串推断近期状态"""
    recent = form_str[:10] if form_str else ""
    wins = recent.count("W")
    draws = recent.count("D")
    losses = recent.count("L")
    total = wins + draws + losses
    return {
        "form": recent,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for_avg": 0.0,
        "goals_against_avg": 0.0,
        "clean_sheet_rate": 0.0,
        "form_score": round((wins * 3 + draws) / (total * 3), 2) if total else 0.5,
    }


def _build_dummy_odds(fixture: dict) -> dict:
    """
    训练时没有实时赔率，用比赛结果反推一个近似赔率。
    这只是为了让 feature_builder 能输出赔率特征。
    """
    goals = fixture.get("goals", {})
    hg = goals.get("home", 0)
    ag = goals.get("away", 0)
    # 用进球数反推一个粗糙的赔率
    total_goals = (hg or 0) + (ag or 0)
    if (hg or 0) > (ag or 0):
        home_prob, draw_prob, away_prob = 0.45, 0.28, 0.27
    elif (hg or 0) == (ag or 0):
        home_prob, draw_prob, away_prob = 0.33, 0.38, 0.29
    else:
        home_prob, draw_prob, away_prob = 0.28, 0.28, 0.44

    return {
        "1x2": _DummyAggregate(home_prob, draw_prob, away_prob, total_goals),
        "asian_handicap": None,
        "over_under": None,
    }


class _DummyAggregate:
    """训练用的简化 MarketAggregate"""
    def __init__(self, home_prob, draw_prob, away_prob, total_goals):
        self.no_vig_probs = {"home": home_prob, "draw": draw_prob, "away": away_prob}
        self.avg_odds = {
            "home": 1 / max(home_prob, 0.01),
            "draw": 1 / max(draw_prob, 0.01),
            "away": 1 / max(away_prob, 0.01),
        }
        self.best_odds = {
            "home": (self.avg_odds["home"], "dummy"),
            "draw": (self.avg_odds["draw"], "dummy"),
            "away": (self.avg_odds["away"], "dummy"),
        }
        self.consensus_score = 50
        self.disagreement_index = 0.0
        self.bookmaker_count = 1
        self.overround = 0.0
        self.return_rate = 1.0


async def _update_model_version(
    version_tag: str,
    metrics: dict[str, float],
    features_hash: str,
    training_samples: int,
) -> None:
    """更新 model_versions 表"""
    from models.model_version import ModelVersion
    from sqlalchemy import select, update

    async with AsyncSessionLocal() as session:
        # 取消旧版本 active
        await session.execute(
            update(ModelVersion).where(ModelVersion.is_active == True).values(is_active=False)
        )
        # 插入新版本
        session.add(ModelVersion(
            version_tag=version_tag,
            model_type="stacking_lgb_xgb_catboost",
            accuracy=metrics.get("accuracy"),
            brier_score=metrics.get("brier_score_home"),
            log_loss=metrics.get("log_loss"),
            features_hash=features_hash,
            training_samples=training_samples,
            is_active=True,
        ))
        await session.commit()
