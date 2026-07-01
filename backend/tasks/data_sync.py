"""
数据同步定时任务
"""

import asyncio
from datetime import datetime, timedelta, timezone

from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal
from models.match import Match
from models.telegram_mvp import Result
from services.telegram_mvp.api_football import ApiFootballClient
from sqlalchemy import select

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.data_sync.sync_odds")
def sync_odds():
    """每5分钟同步赔率数据.

    MVP 中即时分析会保存 odds_snapshots；此任务作为可运行占位，只记录状态。
    """
    logger.info("sync_odds: snapshots are captured during analysis in MVP")


@celery_app.task(name="tasks.data_sync.sync_results")
def sync_results():
    """每30分钟同步比赛结果."""
    return asyncio.run(_sync_results())


async def _sync_results() -> dict:
    api = ApiFootballClient()
    updated = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Match).where(
                    Match.api_fixture_id.is_not(None),
                    Match.match_date <= now + timedelta(hours=3),
                )
            )
        ).scalars().all()

        for match in rows:
            fixture = api.fixture_by_id(match.api_fixture_id)
            if not fixture:
                continue
            status = fixture.get("fixture", {}).get("status", {}).get("short", "")
            goals = fixture.get("goals", {})
            score = fixture.get("score", {})
            match.status = status
            match.home_score = goals.get("home")
            match.away_score = goals.get("away")
            match.ht_home_score = score.get("halftime", {}).get("home")
            match.ht_away_score = score.get("halftime", {}).get("away")
            existing = (
                await session.execute(select(Result).where(Result.fixture_id == match.api_fixture_id))
            ).scalar_one_or_none()
            if existing:
                existing.home_goals = goals.get("home")
                existing.away_goals = goals.get("away")
                existing.halftime_home = score.get("halftime", {}).get("home")
                existing.halftime_away = score.get("halftime", {}).get("away")
                existing.status = status
            else:
                session.add(
                    Result(
                        fixture_id=match.api_fixture_id,
                        home_goals=goals.get("home"),
                        away_goals=goals.get("away"),
                        halftime_home=score.get("halftime", {}).get("home"),
                        halftime_away=score.get("halftime", {}).get("away"),
                        status=status,
                    )
                )
            updated += 1
        await session.commit()
    logger.info("sync_results updated=%s", updated)
    return {"updated": updated}


@celery_app.task(name="tasks.data_sync.recalculate_elo")
def recalculate_elo():
    """每日ELO重算 → 待实现"""
    logger.info("recalculate_elo: deferred in Telegram MVP")


@celery_app.task(name="tasks.data_sync.generate_features")
def generate_features():
    """每日特征工程 → 待实现"""
    logger.info("generate_features: deferred in Telegram MVP")
