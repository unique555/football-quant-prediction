"""
赔率路由 — 实时赔率查询
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/odds/{match_id}")
async def match_odds(match_id: str):
    """单场实时赔率 → 待实现"""
    return {"status": "not_implemented", "match_id": match_id}
