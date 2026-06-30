"""
Pydantic Schema: 联赛 & 球队
"""
from typing import List, Optional

from pydantic import BaseModel


class TeamSimple(BaseModel):
    id: int
    name: str
    elo_rating: float


class LeagueResponse(BaseModel):
    id: int
    name: str
    country: str
    tier: int


class StandingsEntry(BaseModel):
    rank: int
    team: TeamSimple
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    goal_diff: int
    points: int
