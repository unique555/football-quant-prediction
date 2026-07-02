# 已废弃的根目录脚本

以下脚本已由 `backend/` 内的 Celery 任务 / FastAPI 路由替代，
不再维护。保留文件仅供历史参考，请勿在新代码中 import。

| 废弃脚本 | 替代实现 |
|---------|---------|
| `run_daily.py` | `backend/tasks/auto_analyze.py` |
| `predict_match.py` | `backend/api/routes/predict.py` + `PredictionService` |
| `predict_live.py` | 暂未替代（后续需要时在 backend 内重建） |
| `predict_worldcup.py` | 合并进统一管线 `auto_analyze` |
| `predict_all_leagues.py` | 合并进 `auto_analyze` |
| `run_analysis.py` | `backend/tasks/daily_review.py`（Phase 1） |
| `run_weekly.py` | `backend/tasks/daily_report.py`（已有框架） |
| `run_live_test.py` | 废弃 |
| `scheduler.py` | Celery beat (`backend/tasks/celery_app.py`) |
| `scrape_football_data.py` | 数据源切 API-Football，赛程由 `sync_fixtures` 负责 |
| `build_football_data_db.py` | 同上 |
| `build_history_db.py` | 同上 |
| `backtest_ml.py` | `backend/tasks/historical_backtest.py`（Phase 3） |
| `backtest_runner.py` | 同上 |
| `bot.py` | `bot_app/main.py`（已有） |
| `config.py` | `backend/core/config.py`（已有） |
| `notify.py` | `backend/services/notify.py`（新建） |
| `utils.py` | 按需迁移到 backend |
| `model/trainer.py` | Phase 2 ML 训练管线替代 |
| `model/national_trainer.py` | 同上 |
