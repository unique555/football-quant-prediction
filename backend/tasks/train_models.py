"""
模型训练定时任务
"""

from celery.utils.log import get_task_logger

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)


@celery_app.task(name="tasks.train_models.retrain_all")
def retrain_all():
    """每周全量重训练所有模型（MVP：外部模型训练延后）."""
    logger.info("retrain_all: deferred in Telegram MVP")
    return {"status": "deferred"}
