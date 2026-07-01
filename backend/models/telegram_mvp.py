"""
SQLAlchemy ORM models for the Telegram-first MVP.
"""

from core.database import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB


class TeamAlias(Base):
    __tablename__ = "team_aliases"
    __table_args__ = (UniqueConstraint("alias_key", name="uq_team_aliases_alias_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    alias = Column(String(200), nullable=False)
    alias_key = Column(String(200), nullable=False)
    api_team_id = Column(Integer)
    api_team_name = Column(String(200), nullable=False)
    lang = Column(String(20), default="unknown")
    country = Column(String(100))
    created_at = Column(DateTime, server_default=func.now())


class OddsSnapshot(Base):
    __tablename__ = "odds_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, nullable=False, index=True)
    snapshot_type = Column(String(30), nullable=False, default="latest")
    market = Column(String(40), nullable=False, default="1x2")
    bookmaker = Column(String(100))
    home_odds = Column(Float)
    draw_odds = Column(Float)
    away_odds = Column(Float)
    ah_line = Column(Float)
    ah_home_odds = Column(Float)
    ah_away_odds = Column(Float)
    ou_line = Column(Float)
    over_odds = Column(Float)
    under_odds = Column(Float)
    raw_json = Column(JSONB)
    captured_at = Column(DateTime, server_default=func.now(), index=True)


class ValueCandidate(Base):
    __tablename__ = "value_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, nullable=False, index=True)
    market = Column(String(40), nullable=False)
    pick = Column(String(80), nullable=False)
    display_pick = Column(String(120), nullable=False)
    prob = Column(Float)
    odds = Column(Float)
    market_prob = Column(Float)
    edge = Column(Float)
    ev = Column(Float)
    kelly = Column(Float)
    risk = Column(String(20), default="中")
    bookmaker_count = Column(Integer, default=0)
    consensus_score = Column(Integer, default=0)
    disagreement_index = Column(Float, default=0.0)
    value_score = Column(Integer, default=0)
    selected = Column(Boolean, default=False)
    reason = Column(Text)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("fixture_id", name="uq_results_fixture_id"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    fixture_id = Column(Integer, nullable=False, index=True)
    home_goals = Column(Integer)
    away_goals = Column(Integer)
    halftime_home = Column(Integer)
    halftime_away = Column(Integer)
    status = Column(String(30), nullable=False, default="pending")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("user_id", "fixture_id", name="uq_subscriptions_user_fixture"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(80), nullable=False)
    chat_id = Column(String(80), nullable=False)
    fixture_id = Column(Integer, nullable=False, index=True)
    notify_t6 = Column(Boolean, default=True)
    notify_t1 = Column(Boolean, default=True)
    notify_result = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
