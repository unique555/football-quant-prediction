"""
数据同步定时任务
"""
from celery.utils.log import get_task_logger

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.data_sync.sync_odds")
def sync_odds():
    """每5分钟同步赔率数据 → 待实现"""
    logger.info("sync_odds: not implemented")


@celery_app.task(name="tasks.data_sync.sync_results")
def sync_results():
    """每30分钟同步比赛结果 → 待实现"""
    logger.info("sync_results: not implemented")


@celery_app.task(name="tasks.data_sync.recalculate_elo")
def recalculate_elo():
    """每日ELO重算 → 待实现"""
    logger.info("recalculate_elo: not implemented")


@celery_app.task(name="tasks.data_sync.generate_features")
def generate_features():
    """每日特征工程 → 待实现"""
    logger.info("generate_features: not implemented")
