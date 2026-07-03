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
        "tasks.sync_fixtures",
        "tasks.auto_analyze",
        "tasks.value_screener",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # --- 比赛发现（每 6 小时） ---
        "sync-fixtures-every-6h": {
            "task": "tasks.sync_fixtures.discover",
            "schedule": crontab(minute="0", hour="*/6"),
        },
        # --- 赔率采集 ---
        "sync-odds-every-5min": {
            "task": "tasks.data_sync.sync_odds",
            "schedule": crontab(minute="*/5"),
        },
        # --- 自动分析（每 3 小时） ---
        "auto-analyze-every-3h": {
            "task": "tasks.auto_analyze.run",
            "schedule": crontab(minute="0", hour="*/3"),
        },
        # --- 价值筛选+推送（每 3 小时，分析后 30 分钟） ---
        "value-screener-every-3h": {
            "task": "tasks.value_screener.run",
            "schedule": crontab(minute="30", hour="*/3"),
        },
        # --- 结果同步+结算 ---
        "sync-results-every-30min": {
            "task": "tasks.data_sync.sync_results",
            "schedule": crontab(minute="*/30"),
        },
        # --- 队名别名刷新 ---
        "refresh-team-alias-file-daily": {
            "task": "tasks.data_sync.refresh_team_alias_file",
            "schedule": crontab(hour=2, minute=20),
        },
        # --- 模型重训练（每周一，Phase 2 启用） ---
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
