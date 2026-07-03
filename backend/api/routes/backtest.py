"""
回测路由 — 发起回测、查看报告
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/backtest/run")
async def run_backtest():
    """发起回测任务 → 待实现"""
    return {"status": "not_implemented"}


@router.get("/backtest/{task_id}/status")
async def backtest_status(task_id: str):
    """回测状态查询 → 待实现"""
    return {"status": "not_implemented", "task_id": task_id}


@router.get("/backtest/{task_id}/report")
async def backtest_report(task_id: str):
    """回测报告 → 待实现"""
    return {"status": "not_implemented", "task_id": task_id}
