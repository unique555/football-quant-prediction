"""
日报/周报生成任务
"""
from celery.utils.log import get_task_logger

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.daily_report.generate_weekly_report")
def generate_weekly_report():
    """生成每周分析报告 → 待实现"""
    logger.info("generate_weekly_report: not implemented")
