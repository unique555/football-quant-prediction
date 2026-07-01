"""
日报/周报生成任务
"""

import asyncio

from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal
from services.telegram_mvp.pipeline import performance_summary, stats_summary

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.daily_report.generate_weekly_report")
def generate_weekly_report():
    """生成每周分析报告（MVP：记录统计摘要到日志）."""
    return asyncio.run(_weekly_summary())


async def _weekly_summary() -> dict:
    async with AsyncSessionLocal() as session:
        summary = await stats_summary(session)
        performance = await performance_summary(session)
    payload = {"summary": summary, "performance": performance}
    logger.info("weekly review: %s", payload)
    return payload
