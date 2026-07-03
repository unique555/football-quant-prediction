"""
赛程同步定时任务 — 调用比赛发现引擎，自动拉取未来 7 天赛程入库。
"""

from __future__ import annotations

import asyncio
import logging

from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal
from services.fixture_discovery import FixtureDiscovery

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.sync_fixtures.discover")
def discover_fixtures(days_ahead: int = 7) -> dict:
    """定时赛程发现任务 — 每 6 小时运行一次"""
    return asyncio.run(_discover(days_ahead))


async def _discover(days_ahead: int) -> dict:
    async with AsyncSessionLocal() as session:
        discovery = FixtureDiscovery()
        stats = await discovery.discover(session, days_ahead=days_ahead)
    logger.info("sync_fixtures result: %s", stats)
    return stats
