"""
Pydantic Schema: 比赛
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MatchResponse(BaseModel):
    id: int
    home_team: str
    away_team: str
    league: str
    match_date: datetime
    status: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
