"""
模型训练定时任务
"""

from celery.utils.log import get_task_logger

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.train_models.retrain_all")
def retrain_all():
    """每周全量重训练所有模型 → 待实现"""
    logger.info("retrain_all: not implemented")
