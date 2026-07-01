"""Prediction service that adapts API-Football data into the engine pipeline."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import ValueCandidate
from sqlalchemy.ext.asyncio import AsyncSession

from engine.asian.asian_analyzer import AsianLine
from engine.consensus.consensus_analyzer import BookmakerSnapshot
from engine.orchestrator.pipeline import (
    FinalReport,
    generate_markdown_report,
    run_full_pipeline,
)
from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.names import (
    MatchQuery,
    normalize_key,
    normalize_team_name,
    parse_match_text,
)
from services.telegram_mvp.odds import (
    BookmakerOdds,
    MarketAggregate,
    aggregate_1x2,
    aggregate_two_way,
    no_vig_probs,
    parse_api_football_odds,
)
from services.telegram_mvp.pipeline import (
    PipelineResult,
    _estimate_model_probs,
    _fixture_to_match_dict,
    _fixtures_by_team_fallback,
    format_analysis_message,
    load_alias_team_ids,
    load_aliases,
    load_recent_odds_snapshots,
    lookup_fixture_cache,
    persist_odds_snapshots,
    rank_fixture_candidates,
    remember_fixture_cache,
    remember_query_aliases,
    should_return_candidates,
    upsert_match,
)
from services.telegram_mvp.value import ModelProbabilities, select_value_candidates

SHANGHAI_TZ = timezone.utc
MODEL_VERSION = "engine-orchestrator-2026-07-01"
FIXTURE_DAYS_BEFORE = 1
FIXTURE_DAYS_AFTER = 5

BOOKMAKER_ENGINE_NAMES = {
    "Pinnacle": "pinnacle",
    "Bet365": "bet365",
    "Betfair": "betfair",
    "1xBet": "1xbet",
    "WilliamHill": "william_hill",
    "Marathonbet": "marathon",
    "188Bet": "188bet",
    "Bwin": "bwin",
    "Unibet": "unibet",
    "10Bet": "10bet",
}


def _engine_bookmaker_name(name: str) -> str:
    cleaned = (name or "").strip()
    if cleaned in BOOKMAKER_ENGINE_NAMES:
        return BOOKMAKER_ENGINE_NAMES[cleaned]
    return normalize_key(cleaned).replace(" ", "_")


def _bookmaker_snapshot(row: BookmakerOdds) -> BookmakerSnapshot | None:
    if not (row.home and row.draw and row.away):
        return None
    probs = no_vig_probs([float(row.home), float(row.draw), float(row.away)])
    if len(probs) != 3:
        return None
    payout = 1 / (1 / row.home + 1 / row.draw + 1 / row.away)
    return BookmakerSnapshot(
        name=_engine_bookmaker_name(row.bookmaker),
        home_odds=float(row.home),
        draw_odds=float(row.draw),
        away_odds=float(row.away),
        implied_home_prob=probs[0],
        implied_draw_prob=probs[1],
        implied_away_prob=probs[2],
        payout_rate=payout,
    )


def _bookmaker_snapshots(parsed_odds: list[BookmakerOdds]) -> list[BookmakerSnapshot]:
    snapshots = []
    seen = set()
    for row in parsed_odds:
        if row.market != "1x2" or row.bookmaker in seen:
            continue
        snapshot = _bookmaker_snapshot(row)
        if snapshot:
            snapshots.append(snapshot)
            seen.add(row.bookmaker)
    return snapshots


def _best_1x2_odds(
    aggregate: MarketAggregate | None,
) -> tuple[float | None, float | None, float | None]:
    if not aggregate:
        return None, None, None
    return (
        aggregate.best_odds.get("home", (None, ""))[0],
        aggregate.best_odds.get("draw", (None, ""))[0],
        aggregate.best_odds.get("away", (None, ""))[0],
    )


def _avg_1x2_odds(aggregate: MarketAggregate | None) -> tuple[float, float, float] | None:
    if not aggregate:
        return None
    return (
        float(aggregate.avg_odds["home"]),
        float(aggregate.avg_odds["draw"]),
        float(aggregate.avg_odds["away"]),
    )


def _asian_lines(aggregate: MarketAggregate | None) -> list[AsianLine] | None:
    if not aggregate:
        return None
    lines = []
    for row in aggregate.raw_bookmakers:
        if row.line is None or row.home is None or row.away is None:
            continue
        lines.append(
            AsianLine(
                handicap=float(row.line),
                home_water=float(row.home),
                away_water=float(row.away),
                bookmaker=_engine_bookmaker_name(row.bookmaker),
            )
        )
    return lines or None


def _model_probs_for_engine(model_probs: ModelProbabilities) -> tuple[float, float, float]:
    return model_probs.home, model_probs.draw, model_probs.away


def _confidence_text(score: float) -> str:
    if score >= 0.10:
        return "高"
    if score >= 0.05:
        return "中"
    return "低"


def _risk_text(report: FinalReport) -> str:
    if report.final_verdict.value in {"high_confidence", "moderate"} and not report.warnings:
        return "低"
    if report.final_verdict.value == "skip" or len(report.warnings) >= 2:
        return "高"
    return "中"


def _pick_label(report: FinalReport) -> tuple[str | None, str | None]:
    direction = report.recommended_direction
    if not direction:
        return None, None
    display = {
        "home": f"胜平负：{report.home_team}",
        "draw": "胜平负：平局",
        "away": f"胜平负：{report.away_team}",
    }.get(direction)
    return direction, display


def _selected_candidate_fields(
    report: FinalReport,
    aggregate: MarketAggregate | None,
) -> dict[str, Any]:
    pick, display_pick = _pick_label(report)
    if not pick or not aggregate:
        return {}
    odds, bookmaker = aggregate.best_odds.get(pick, (None, None))
    probs = {
        "home": report.final_home_prob,
        "draw": report.final_draw_prob,
        "away": report.final_away_prob,
    }
    market_prob = aggregate.no_vig_probs.get(pick, 0.0)
    prob = probs[pick]
    odds_value = float(odds or 0)
    ev = prob * odds_value - 1 if odds_value else None
    edge = prob - market_prob
    kelly = (prob * odds_value - 1) / (odds_value - 1) if odds_value > 1 else 0.0
    return {
        "market": "1x2",
        "pick": pick,
        "display_pick": display_pick,
        "bookmaker": bookmaker,
        "odds": odds_value or None,
        "ev": round(ev, 4) if ev is not None else None,
        "kelly": round(max(0.0, kelly), 4),
        "edge": round(edge, 4),
        "market_prob": round(market_prob, 4),
        "value_score": round(report.confidence_score * 100),
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value


def _persist_engine_prediction(
    session: AsyncSession,
    match: Match,
    model_probs: ModelProbabilities,
    report: FinalReport,
    report_text: str,
    selected_fields: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    session.add(
        Prediction(
            match_id=match.id,
            fixture_id=match.api_fixture_id,
            model_version=MODEL_VERSION,
            model_name="engine-orchestrator",
            home_win_prob=report.final_home_prob,
            draw_prob=report.final_draw_prob,
            away_win_prob=report.final_away_prob,
            confidence=report.confidence_score,
            best_market=selected_fields.get("market"),
            best_pick=selected_fields.get("pick"),
            best_display_pick=selected_fields.get("display_pick"),
            best_bookmaker=selected_fields.get("bookmaker"),
            best_odds=selected_fields.get("odds"),
            best_ev=selected_fields.get("ev"),
            best_kelly=selected_fields.get("kelly"),
            best_edge=selected_fields.get("edge"),
            market_prob=selected_fields.get("market_prob"),
            value_score=selected_fields.get("value_score", 0),
            confidence_text=_confidence_text(report.confidence_score),
            risk=_risk_text(report),
            settled_status="pending",
            report_text=report_text,
            raw_json={
                "engine_report": _jsonable(report),
                "input_model_probs": model_probs.__dict__,
                "payload": payload,
            },
        )
    )


def _persist_engine_candidate(
    session: AsyncSession,
    fixture_id: int,
    report: FinalReport,
    aggregate: MarketAggregate | None,
    selected_fields: dict[str, Any],
) -> None:
    if not selected_fields:
        return
    session.add(
        ValueCandidate(
            fixture_id=fixture_id,
            market=selected_fields.get("market"),
            pick=selected_fields.get("pick"),
            display_pick=selected_fields.get("display_pick"),
            best_bookmaker=selected_fields.get("bookmaker"),
            prob={
                "home": report.final_home_prob,
                "draw": report.final_draw_prob,
                "away": report.final_away_prob,
            }.get(selected_fields.get("pick"), 0),
            odds=selected_fields.get("odds"),
            market_prob=selected_fields.get("market_prob"),
            edge=selected_fields.get("edge"),
            ev=selected_fields.get("ev"),
            kelly=selected_fields.get("kelly"),
            risk=_risk_text(report),
            bookmaker_count=aggregate.bookmaker_count if aggregate else 0,
            consensus_score=round(
                (report.consensus.direction_strength if report.consensus else 0) * 100
            ),
            disagreement_index=0.0,
            data_quality_score=round(
                (report.consensus.data_quality if report.consensus else 0) * 100
            ),
            value_score=selected_fields.get("value_score", 0),
            selected=True,
            reason=report.summary,
            settled_status="pending",
        )
    )


def _engine_message(report: FinalReport, mvp_message: str) -> str:
    engine_text = generate_markdown_report(report)
    return f"{engine_text}\n\n---\n\n## 市场价值候选\n\n{mvp_message}"


class PredictionService:
    """Resolve fixtures with Telegram MVP helpers, then analyze with the engine."""

    def __init__(self, api_client: ApiFootballClient | None = None):
        self.api = api_client or ApiFootballClient()

    async def resolve_text(self, session: AsyncSession, text: str) -> PipelineResult:
        query = parse_match_text(text)
        if not query:
            return PipelineResult("error", "❌ 格式: /分析 法国 vs 瑞典")

        query = await self._normalize_query(session, query)
        cached_fixture_id = await lookup_fixture_cache(session, query)
        if cached_fixture_id:
            return await self.analyze_fixture(session, cached_fixture_id, source_query=query)

        fixtures = self.api.fixtures_by_date_window(
            datetime.now(timezone.utc),
            days_before=FIXTURE_DAYS_BEFORE,
            days_after=FIXTURE_DAYS_AFTER,
        )
        candidates = rank_fixture_candidates(fixtures, query)
        if not candidates:
            alias_team_ids = await load_alias_team_ids(session)
            candidates = rank_fixture_candidates(
                _fixtures_by_team_fallback(self.api, query, alias_team_ids),
                query,
            )
        if not candidates:
            return PipelineResult("not_found", f"❌ API-Football 未找到比赛: {query.raw}")
        if should_return_candidates(candidates):
            from services.telegram_mvp.fixtures import format_candidate_list

            return PipelineResult(
                "candidates", format_candidate_list(candidates), candidates=candidates
            )

        await remember_fixture_cache(session, query, candidates[0])
        return await self.analyze_fixture(session, candidates[0].fixture_id, source_query=query)

    async def analyze_fixture(
        self,
        session: AsyncSession,
        fixture_id: int,
        source_query: MatchQuery | None = None,
    ) -> PipelineResult:
        fixture = self.api.fixture_by_id(fixture_id)
        if not fixture:
            return PipelineResult("not_found", f"❌ API-Football 未找到 fixture_id={fixture_id}")

        match = await upsert_match(session, fixture)
        if source_query:
            await remember_query_aliases(session, source_query, fixture)

        parsed_odds = await load_recent_odds_snapshots(session, fixture_id)
        fetched_fresh = False
        if not parsed_odds:
            parsed_odds = parse_api_football_odds(self.api.odds_by_fixture(fixture_id))
            fetched_fresh = True

        aggregates = {
            "1x2": aggregate_1x2(parsed_odds),
            "asian_handicap": aggregate_two_way(parsed_odds, "asian_handicap"),
            "over_under": aggregate_two_way(parsed_odds, "over_under"),
        }
        prediction_response = self.api.get("/predictions", {"fixture": fixture_id}).get(
            "response", []
        )
        model_probs = _estimate_model_probs(
            aggregates["1x2"],
            prediction_response[0] if prediction_response else None,
        )
        report = self._run_engine(match, aggregates, parsed_odds, model_probs)
        candidates = select_value_candidates(fixture_id, model_probs, aggregates)
        mvp_message = format_analysis_message(match, aggregates, candidates)
        message = _engine_message(report, mvp_message)
        selected_fields = _selected_candidate_fields(report, aggregates["1x2"])

        if fetched_fresh:
            await persist_odds_snapshots(session, fixture_id, parsed_odds)
        _persist_engine_candidate(session, fixture_id, report, aggregates["1x2"], selected_fields)
        _persist_engine_prediction(
            session,
            match,
            model_probs,
            report,
            message,
            selected_fields,
            {
                "match": _fixture_to_match_dict(fixture),
                "value_candidates": [item.asdict() for item in candidates],
            },
        )
        await session.commit()

        return PipelineResult(
            "ok",
            message,
            fixture_id=fixture_id,
            payload={
                "match": _fixture_to_match_dict(fixture),
                "engine": _jsonable(report),
                "value_candidates": [item.asdict() for item in candidates],
            },
        )

    async def _normalize_query(self, session: AsyncSession, query: MatchQuery) -> MatchQuery:
        aliases = await load_aliases(session)
        if not aliases:
            return query
        return MatchQuery(
            home=normalize_team_name(query.home, aliases),
            away=normalize_team_name(query.away, aliases),
            raw=query.raw,
            raw_home=query.raw_home,
            raw_away=query.raw_away,
        )

    def _run_engine(
        self,
        match: Match,
        aggregates: dict[str, MarketAggregate | None],
        parsed_odds: list[BookmakerOdds],
        model_probs: ModelProbabilities,
    ) -> FinalReport:
        one_x_two = aggregates.get("1x2")
        ah = aggregates.get("asian_handicap")
        model_home, model_draw, model_away = _model_probs_for_engine(model_probs)
        best_home, best_draw, best_away = _best_1x2_odds(one_x_two)
        initial_odds = _avg_1x2_odds(one_x_two)
        asian_handicap = float(ah.avg_odds["line"]) if ah and "line" in ah.avg_odds else None

        return run_full_pipeline(
            home_team=match.home_team_name or "",
            away_team=match.away_team_name or "",
            league=match.league_name or "",
            tsi_home=50,
            tsi_away=50,
            asian_handicap=asian_handicap,
            initial_odds=initial_odds,
            match_date=match.match_date,
            bookmaker_snapshots=_bookmaker_snapshots(parsed_odds),
            model_home_prob=model_home,
            model_draw_prob=model_draw,
            model_away_prob=model_away,
            best_home_odds=best_home,
            best_draw_odds=best_draw,
            best_away_odds=best_away,
            current_asian_lines=_asian_lines(ah),
        )

    async def predict_single(
        self, session: AsyncSession, home_team: str, away_team: str
    ) -> PipelineResult:
        return await self.resolve_text(session, f"{home_team} vs {away_team}")

    async def predict_batch(self, session: AsyncSession, league: str) -> list[dict]:
        raise NotImplementedError("Batch prediction is not implemented yet")
