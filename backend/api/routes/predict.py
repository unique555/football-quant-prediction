"""
预测路由 — 单场 & 批量预测
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/predict")
async def predict_match():
    """单场比赛预测 → 待实现"""
    return {"status": "not_implemented", "endpoint": "/v1/predict"}


@router.post("/predict/batch")
async def predict_batch():
    """批量预测（一轮比赛）→ 待实现"""
    return {"status": "not_implemented", "endpoint": "/v1/predict/batch"}
