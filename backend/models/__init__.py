"""Register all ORM models on the shared SQLAlchemy metadata."""

from models.league import League
from models.match import Match
from models.model_version import ModelVersion
from models.odds import Odds
from models.prediction import Prediction
from models.team import Team
from models.telegram_mvp import (
    FixtureAlias,
    OddsSnapshot,
    Result,
    Subscription,
    TeamAlias,
    ValueCandidate,
)
from models.user import User

__all__ = [
    "League",
    "FixtureAlias",
    "Match",
    "ModelVersion",
    "Odds",
    "OddsSnapshot",
    "Prediction",
    "Result",
    "Subscription",
    "Team",
    "TeamAlias",
    "User",
    "ValueCandidate",
]
