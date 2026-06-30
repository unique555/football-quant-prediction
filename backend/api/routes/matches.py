"""
比赛路由 — 赛程、详情、H2H
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/matches")
async def list_matches():
    """赛程查询 → 待实现"""
    return {"status": "not_implemented"}


@router.get("/matches/{match_id}")
async def match_detail(match_id: str):
    """比赛详情 → 待实现"""
    return {"status": "not_implemented", "match_id": match_id}


@router.get("/teams/{team_id}/profile")
async def team_profile(team_id: str):
    """球队画像 → 待实现"""
    return {"status": "not_implemented", "team_id": team_id}


@router.get("/teams/{team_id}/h2h/{opponent_id}")
async def head_to_head(team_id: str, opponent_id: str):
    """历史交锋 → 待实现"""
    return {"status": "not_implemented", "team_id": team_id, "opponent_id": opponent_id}
