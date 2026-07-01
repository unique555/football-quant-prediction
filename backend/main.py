"""
FastAPI 应用入口
"""

from contextlib import asynccontextmanager

from api.deps import get_db
from api.routes import backtest, leagues, matches, models_route, odds, predict
from core.config import settings
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.telegram_mvp.pipeline import performance_summary, stats_summary
from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    yield
    # 关闭时


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(predict.router, prefix="/v1", tags=["预测"])
app.include_router(leagues.router, prefix="/v1", tags=["联赛"])
app.include_router(matches.router, prefix="/v1", tags=["比赛"])
app.include_router(odds.router, prefix="/v1", tags=["赔率"])
app.include_router(backtest.router, prefix="/v1", tags=["回测"])
app.include_router(models_route.router, prefix="/v1", tags=["模型"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/v1/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    return await stats_summary(db)


@app.get("/v1/stats/performance")
async def stats_performance(db: AsyncSession = Depends(get_db)):
    return await performance_summary(db)
