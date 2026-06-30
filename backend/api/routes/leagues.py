"""
联赛路由 — 联赛列表、积分榜、球队
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/leagues")
async def list_leagues():
    """联赛列表 → 待实现"""
    return {"status": "not_implemented"}


@router.get("/leagues/{league_id}/standings")
async def league_standings(league_id: str):
    """积分榜 → 待实现"""
    return {"status": "not_implemented", "league_id": league_id}


@router.get("/leagues/{league_id}/teams")
async def league_teams(league_id: str):
    """联赛球队 → 待实现"""
    return {"status": "not_implemented", "league_id": league_id}
