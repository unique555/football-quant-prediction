"""
Celery 应用配置
"""
from celery import Celery
from celery.schedules import crontab

from core.config import settings

celery_app = Celery(
    "football_quant",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "tasks.data_sync",
        "tasks.train_models",
        "tasks.daily_report",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # --- 数据同步 ---
        "sync-odds-every-5min": {
            "task": "tasks.data_sync.sync_odds",
            "schedule": crontab(minute="*/5"),
        },
        "sync-results-every-30min": {
            "task": "tasks.data_sync.sync_results",
            "schedule": crontab(minute="*/30"),
        },
        # --- 特征 & 模型 ---
        "recalculate-elo-daily": {
            "task": "tasks.data_sync.recalculate_elo",
            "schedule": crontab(hour=0, minute=0),
        },
        "generate-features-daily": {
            "task": "tasks.data_sync.generate_features",
            "schedule": crontab(hour=1, minute=0),
        },
        # --- 模型重训练（每周一） ---
        "retrain-models-weekly": {
            "task": "tasks.train_models.retrain_all",
            "schedule": crontab(hour=6, minute=0, day_of_week=1),
        },
        # --- 周报 ---
        "weekly-report": {
            "task": "tasks.daily_report.generate_weekly_report",
            "schedule": crontab(hour=10, minute=0, day_of_week=1),
        },
    },
)
