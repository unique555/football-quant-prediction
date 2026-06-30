"""
模型路由 — 模型列表、指标、版本
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/models")
async def list_models():
    """模型列表 → 待实现"""
    return {"status": "not_implemented"}


@router.get("/models/{model_id}/metrics")
async def model_metrics(model_id: str):
    """模型评估指标 → 待实现"""
    return {"status": "not_implemented", "model_id": model_id}
