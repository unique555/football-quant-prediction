"""Scheduled data synchronization and settlement tasks."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from celery.utils.log import get_task_logger
from core.database import AsyncSessionLocal
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import Result, Subscription, TeamAlias, ValueCandidate
from services.telegram_mvp.alias_builder import default_output_path, refresh_alias_file
from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.names import normalize_key
from services.telegram_mvp.odds import parse_api_football_odds
from services.telegram_mvp.pipeline import persist_odds_snapshots
from services.telegram_mvp.settlement import (
    profit_units,
    settle_1x2,
    settle_asian_handicap,
    settle_over_under,
    settlement_text,
)
from sqlalchemy import or_, select

from tasks.celery_app import celery_app

logger = get_task_logger(__name__)
FINISHED_STATUSES = {"FT", "AET", "PEN"}


@celery_app.task(name="tasks.data_sync.sync_odds")
def sync_odds():
    """Capture T-24/T-12/T-6/latest odds snapshots for known upcoming fixtures."""
    return asyncio.run(_sync_odds())


@celery_app.task(name="tasks.data_sync.refresh_team_alias_file")
def refresh_team_alias_file():
    """Refresh generated Chinese team aliases and import them into Postgres."""
    return asyncio.run(_refresh_team_alias_file())


async def _refresh_team_alias_file() -> dict:
    summary = refresh_alias_file(output=default_output_path(), days_before=1, days_after=14)
    output = Path(summary["output"])
    async with AsyncSessionLocal() as session:
        summary["db_aliases_upserted"] = await import_alias_file_to_db(session, output)
        await session.commit()
    logger.info("refresh_team_alias_file summary=%s", summary)
    return summary


async def import_alias_file_to_db(session, path: Path) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    count = 0
    for record in payload.get("aliases", []):
        api_team_name = str(record.get("api_team_name") or "").strip()
        if not api_team_name:
            continue
        api_team_id = record.get("api_team_id")
        country = record.get("country")
        for alias in record.get("aliases") or []:
            alias = str(alias).strip()
            key = normalize_key(alias)
            if not key or key == normalize_key(api_team_name):
                continue
            existing = (
                await session.execute(select(TeamAlias).where(TeamAlias.alias_key == key))
            ).scalar_one_or_none()
            if existing:
                existing.alias = alias
                existing.api_team_name = api_team_name
                existing.api_team_id = int(api_team_id) if api_team_id else None
                existing.lang = "zh"
                existing.country = country
            else:
                session.add(
                    TeamAlias(
                        alias=alias,
                        alias_key=key,
                        api_team_id=int(api_team_id) if api_team_id else None,
                        api_team_name=api_team_name,
                        lang="zh",
                        country=country,
                    )
                )
            count += 1
    return count


def snapshot_type_for(kickoff: datetime, now: datetime) -> str | None:
    hours = (kickoff - now).total_seconds() / 3600
    windows = (("T-24", 24), ("T-12", 12), ("T-6", 6))
    for label, target in windows:
        if target - 0.5 <= hours <= target + 0.5:
            return label
    if 0 <= hours <= 3:
        return "latest"
    return None


async def _sync_odds() -> dict:
    api = ApiFootballClient()
    captured = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        matches = (
            (
                await session.execute(
                    select(Match).where(
                        Match.api_fixture_id.is_not(None),
                        Match.match_date >= now,
                        Match.match_date <= now + timedelta(hours=25),
                    )
                )
            )
            .scalars()
            .all()
        )
        for match in matches:
            snapshot_type = snapshot_type_for(match.match_date, now)
            if not snapshot_type:
                continue
            odds_response = api.odds_by_fixture(match.api_fixture_id)
            parsed = parse_api_football_odds(odds_response)
            if not parsed:
                continue
            await persist_odds_snapshots(
                session, match.api_fixture_id, parsed, snapshot_type=snapshot_type
            )
            captured += len(parsed)
        await session.commit()
    logger.info("sync_odds captured=%s", captured)
    return {"captured": captured}


@celery_app.task(name="tasks.data_sync.sync_results")
def sync_results():
    """Fetch match results and settle predictions every 30 minutes."""
    return asyncio.run(_sync_results())


async def _sync_results() -> dict:
    api = ApiFootballClient()
    updated = 0
    settled = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(Match).where(
                        Match.api_fixture_id.is_not(None),
                        Match.match_date <= now + timedelta(hours=3),
                    )
                )
            )
            .scalars()
            .all()
        )

        for match in rows:
            fixture = api.fixture_by_id(match.api_fixture_id)
            if not fixture:
                continue
            status = fixture.get("fixture", {}).get("status", {}).get("short", "")
            goals = fixture.get("goals", {})
            score = fixture.get("score", {})
            match.status = status
            match.home_score = goals.get("home")
            match.away_score = goals.get("away")
            match.ht_home_score = score.get("halftime", {}).get("home")
            match.ht_away_score = score.get("halftime", {}).get("away")
            existing = (
                await session.execute(
                    select(Result).where(Result.fixture_id == match.api_fixture_id)
                )
            ).scalar_one_or_none()
            if existing:
                existing.home_goals = goals.get("home")
                existing.away_goals = goals.get("away")
                existing.halftime_home = score.get("halftime", {}).get("home")
                existing.halftime_away = score.get("halftime", {}).get("away")
                existing.status = status
            else:
                session.add(
                    Result(
                        fixture_id=match.api_fixture_id,
                        home_goals=goals.get("home"),
                        away_goals=goals.get("away"),
                        halftime_home=score.get("halftime", {}).get("home"),
                        halftime_away=score.get("halftime", {}).get("away"),
                        status=status,
                    )
                )
            updated += 1
            if (
                status in FINISHED_STATUSES
                and goals.get("home") is not None
                and goals.get("away") is not None
            ):
                settled += await settle_fixture(session, match)
        await session.commit()
    logger.info("sync_results updated=%s settled=%s", updated, settled)
    return {"updated": updated, "settled": settled}


async def settle_fixture(session, match: Match) -> int:
    candidates = (
        (
            await session.execute(
                select(ValueCandidate).where(
                    ValueCandidate.fixture_id == match.api_fixture_id,
                    or_(
                        ValueCandidate.settled_status.is_(None),
                        ValueCandidate.settled_status == "pending",
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    count = 0
    for candidate in candidates:
        status = settle_candidate(candidate, match.home_score, match.away_score)
        candidate.settled_status = status
        candidate.profit_units = profit_units(status, candidate.odds)
        candidate.settlement_note = settlement_text(status)
        candidate.settled_at = datetime.now(timezone.utc).replace(tzinfo=None)
        count += 1
    predictions = (
        (
            await session.execute(
                select(Prediction).where(
                    Prediction.fixture_id == match.api_fixture_id,
                    or_(
                        Prediction.settled_status.is_(None), Prediction.settled_status == "pending"
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    selected_by_key = {
        (item.market, item.pick, item.line): item for item in candidates if item.selected
    }
    for pred in predictions:
        candidate = selected_by_key.get((pred.best_market, pred.best_pick, pred.best_line))
        if candidate:
            pred.settled_status = candidate.settled_status
            pred.profit_units = candidate.profit_units
            pred.settlement_note = candidate.settlement_note
            pred.settled_at = candidate.settled_at
        elif pred.best_market and pred.best_pick:
            status = settle_market(
                pred.best_market, pred.best_pick, pred.best_line, match.home_score, match.away_score
            )
            pred.settled_status = status
            pred.profit_units = profit_units(status, pred.best_odds)
            pred.settlement_note = settlement_text(status)
            pred.settled_at = datetime.now(timezone.utc).replace(tzinfo=None)
    return count


def settle_candidate(candidate: ValueCandidate, home_goals: int, away_goals: int) -> str:
    return settle_market(candidate.market, candidate.pick, candidate.line, home_goals, away_goals)


def settle_market(
    market: str, pick: str, line: float | None, home_goals: int, away_goals: int
) -> str:
    if market == "1x2":
        return settle_1x2(home_goals, away_goals, pick)
    if market == "asian_handicap" and line is not None:
        return settle_asian_handicap(home_goals, away_goals, line, pick)
    if market == "over_under" and line is not None:
        return settle_over_under(home_goals, away_goals, line, pick)
    return "pending"


@celery_app.task(name="tasks.data_sync.send_reminders")
def send_reminders():
    """Placeholder for Telegram reminders; bot task sends actual messages in the bot process."""
    return asyncio.run(_mark_due_reminders())


async def _mark_due_reminders() -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    due = 0
    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(Subscription).where(Subscription.created_at.is_not(None))
                )
            )
            .scalars()
            .all()
        )
        for sub in rows:
            match = (
                await session.execute(select(Match).where(Match.api_fixture_id == sub.fixture_id))
            ).scalar_one_or_none()
            if not match:
                continue
            hours = (match.match_date - now).total_seconds() / 3600
            if sub.notify_t6 and not sub.notified_t6 and 5.8 <= hours <= 6.2:
                due += 1
            if sub.notify_t1 and not sub.notified_t1 and 0.8 <= hours <= 1.2:
                due += 1
        await session.commit()
    return {"due": due}


@celery_app.task(name="tasks.data_sync.recalculate_elo")
def recalculate_elo():
    logger.info("recalculate_elo: deferred in Telegram MVP")


@celery_app.task(name="tasks.data_sync.generate_features")
def generate_features():
    logger.info("generate_features: deferred in Telegram MVP")
