"""End-to-end analysis pipeline used by Telegram, API routes, and tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import models  # noqa: F401  # Ensure foreign-key target tables are registered.
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import OddsSnapshot, TeamAlias, ValueCandidate
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.fixtures import (
    FixtureCandidate,
    format_candidate_list,
    rank_fixture_candidates,
    should_return_candidates,
)
from services.telegram_mvp.names import (
    MatchQuery,
    normalize_key,
    normalize_team_name,
    parse_match_text,
    team_similarity,
)
from services.telegram_mvp.odds import (
    aggregate_1x2,
    aggregate_two_way,
    parse_api_football_odds,
)
from services.telegram_mvp.value import (
    ModelProbabilities,
    ValueCandidateDTO,
    select_value_candidates,
)

SHANGHAI_TZ = timezone(timedelta(hours=8))
MODEL_VERSION = "telegram-mvp-2026-07-01"


@dataclass
class PipelineResult:
    status: str
    message: str
    candidates: list[FixtureCandidate] | None = None
    fixture_id: int | None = None
    payload: dict[str, Any] | None = None


def _parse_dt(date_text: str) -> datetime:
    if not date_text:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(date_text.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def _fixture_to_match_dict(item: dict[str, Any]) -> dict[str, Any]:
    fixture = item.get("fixture", {})
    teams = item.get("teams", {})
    league = item.get("league", {})
    goals = item.get("goals", {})
    score = item.get("score", {})
    return {
        "api_fixture_id": fixture.get("id"),
        "external_id": str(fixture.get("id")),
        "api_league_id": league.get("id"),
        "season": league.get("season"),
        "home_team_name": teams.get("home", {}).get("name", ""),
        "away_team_name": teams.get("away", {}).get("name", ""),
        "league_name": league.get("name", ""),
        "match_date": _parse_dt(fixture.get("date", "")),
        "status": fixture.get("status", {}).get("short", "NS"),
        "home_score": goals.get("home"),
        "away_score": goals.get("away"),
        "ht_home_score": score.get("halftime", {}).get("home"),
        "ht_away_score": score.get("halftime", {}).get("away"),
        "venue": fixture.get("venue", {}).get("name", ""),
    }


async def load_aliases(session: AsyncSession) -> dict[str, str]:
    rows = (await session.execute(select(TeamAlias))).scalars().all()
    return {row.alias: row.api_team_name for row in rows}


def _best_api_team_id(api: ApiFootballClient, team_name: str) -> int | None:
    best_id = None
    best_score = 0.0
    for item in api.teams_search(team_name):
        team = item.get("team", {})
        candidate_name = team.get("name", "")
        score = team_similarity(team_name, candidate_name)
        if normalize_key(team_name) == normalize_key(candidate_name):
            score += 0.05
        if score > best_score:
            best_score = score
            best_id = team.get("id")
    return int(best_id) if best_id and best_score >= 0.72 else None


def _fixtures_by_team_fallback(api: ApiFootballClient, query: MatchQuery) -> list[dict[str, Any]]:
    team_ids = [
        team_id
        for team_id in (
            _best_api_team_id(api, query.home),
            _best_api_team_id(api, query.away),
        )
        if team_id
    ]
    fixtures: list[dict[str, Any]] = []
    seen: set[int] = set()
    for team_id in dict.fromkeys(team_ids):
        for mode, limit in (("next", 30), ("last", 12)):
            for item in api.fixtures_by_team(team_id, mode=mode, limit=limit):
                fixture_id = item.get("fixture", {}).get("id")
                if not fixture_id or fixture_id in seen:
                    continue
                seen.add(int(fixture_id))
                fixtures.append(item)
    return fixtures


async def upsert_match(session: AsyncSession, fixture: dict[str, Any]) -> Match:
    data = _fixture_to_match_dict(fixture)
    existing = (
        await session.execute(select(Match).where(Match.external_id == str(data["api_fixture_id"])))
    ).scalar_one_or_none()
    if existing:
        for key, value in data.items():
            setattr(existing, key, value)
        return existing
    item = Match(**data)
    session.add(item)
    await session.flush()
    return item


def _estimate_model_probs(aggregate, api_prediction: dict[str, Any] | None = None) -> ModelProbabilities:
    if api_prediction:
        percent = api_prediction.get("predictions", {}).get("percent", {})
        try:
            home = float(str(percent.get("home", "0")).rstrip("%")) / 100
            draw = float(str(percent.get("draw", "0")).rstrip("%")) / 100
            away = float(str(percent.get("away", "0")).rstrip("%")) / 100
            if home + draw + away > 0:
                total = home + draw + away
                return ModelProbabilities(home=home / total, draw=draw / total, away=away / total)
        except (TypeError, ValueError):
            pass
    probs = aggregate.no_vig_probs if aggregate else {"home": 0.34, "draw": 0.32, "away": 0.34}
    return ModelProbabilities(
        home=float(probs.get("home", 0.34)),
        draw=float(probs.get("draw", 0.32)),
        away=float(probs.get("away", 0.34)),
        # Conservative defaults: these only become selectable if odds are clearly good.
        over=0.5,
        under=0.5,
        ah_home=0.5,
        ah_away=0.5,
    )


def _confidence_text(score: int) -> str:
    if score >= 80:
        return "高"
    if score >= 60:
        return "中"
    return "低"


def _format_odds_line(aggregate) -> str:
    if not aggregate:
        return "暂无多机构胜平负赔率"
    avg = aggregate.avg_odds
    return (
        f"市场均值：{avg['home']:.2f} / {avg['draw']:.2f} / {avg['away']:.2f}\n"
        f"去水概率：主 {aggregate.no_vig_probs['home']:.1%} / "
        f"平 {aggregate.no_vig_probs['draw']:.1%} / 客 {aggregate.no_vig_probs['away']:.1%}\n"
        f"机构一致性：{aggregate.consensus_score} | 分歧 {aggregate.disagreement_index:.3f}"
    )


def format_analysis_message(match: Match, aggregate, candidates: list[ValueCandidateDTO]) -> str:
    selected = [item for item in candidates if item.selected]
    best = selected[0] if selected else None
    kickoff = match.match_date.replace(tzinfo=timezone.utc).astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M")
    lines = [
        f"📊 {match.home_team_name} vs {match.away_team_name}",
        f"⏰ {kickoff}",
        f"🏆 {match.league_name or 'Unknown'}",
        "",
        "📈 多机构赔率",
        _format_odds_line(aggregate),
        "",
    ]
    if best:
        lines.extend(
            [
                "🎯 最优价值方向",
                best.display_pick,
                "",
                "💰 投资价值",
                f"模型概率：{best.prob:.1%}",
                f"市场均值概率：{best.market_prob:.1%}",
                f"Edge：{best.edge:+.1%}",
                f"最高赔率：{best.odds:.2f}",
                f"EV：{best.ev:+.1%}",
                f"Kelly：{best.kelly:.3f}",
                f"价值评分：{best.value_score}",
                "",
                "🧾 结论",
                f"谨慎参考：{best.display_pick}",
                f"风险：{best.risk}",
            ]
        )
    else:
        lines.extend(
            [
                "🎯 最优价值方向",
                "暂无",
                "",
                "⚠️ 结论",
                "本场暂无明显投资价值，建议观望。",
            ]
        )
        if not aggregate:
            lines.append("原因：未获取到可用多机构胜平负赔率。")
        elif candidates:
            lines.append("原因：EV/Kelly/Edge/机构一致性未同时达标。")
    return "\n".join(lines)


async def persist_odds_snapshots(
    session: AsyncSession,
    fixture_id: int,
    parsed_odds,
    snapshot_type: str = "latest",
) -> None:
    for row in parsed_odds:
        item = OddsSnapshot(
            fixture_id=fixture_id,
            snapshot_type=snapshot_type,
            market=row.market,
            bookmaker=row.bookmaker,
            home_odds=row.home if row.market == "1x2" else None,
            draw_odds=row.draw if row.market == "1x2" else None,
            away_odds=row.away if row.market == "1x2" else None,
            ah_line=row.line if row.market == "asian_handicap" else None,
            ah_home_odds=row.home if row.market == "asian_handicap" else None,
            ah_away_odds=row.away if row.market == "asian_handicap" else None,
            ou_line=row.line if row.market == "over_under" else None,
            over_odds=row.over if row.market == "over_under" else None,
            under_odds=row.under if row.market == "over_under" else None,
            raw_json=row.raw,
        )
        session.add(item)


async def persist_candidates(session: AsyncSession, candidates: list[ValueCandidateDTO]) -> None:
    for candidate in candidates:
        session.add(ValueCandidate(**candidate.asdict()))


async def persist_prediction(
    session: AsyncSession,
    match: Match,
    model_probs: ModelProbabilities,
    message: str,
    candidates: list[ValueCandidateDTO],
) -> None:
    selected = next((item for item in candidates if item.selected), None)
    session.add(
        Prediction(
            match_id=match.id,
            fixture_id=match.api_fixture_id,
            model_version=MODEL_VERSION,
            model_name="api-football-market-blend",
            home_win_prob=model_probs.home,
            draw_prob=model_probs.draw,
            away_win_prob=model_probs.away,
            confidence=max(model_probs.home, model_probs.draw, model_probs.away),
            best_market=selected.market if selected else None,
            best_pick=selected.pick if selected else None,
            best_display_pick=selected.display_pick if selected else None,
            best_odds=selected.odds if selected else None,
            best_ev=selected.ev if selected else None,
            best_kelly=selected.kelly if selected else None,
            value_score=selected.value_score if selected else 0,
            confidence_text=_confidence_text(selected.value_score) if selected else "低",
            risk=selected.risk if selected else "中",
            report_text=message,
            raw_json={
                "model_probs": model_probs.__dict__,
                "selected": selected.asdict() if selected else None,
            },
        )
    )


class TelegramAnalysisPipeline:
    def __init__(self, api_client: ApiFootballClient | None = None):
        self.api = api_client or ApiFootballClient()

    async def resolve_text(self, session: AsyncSession, text: str) -> PipelineResult:
        query = parse_match_text(text)
        if not query:
            return PipelineResult("error", "❌ 格式: /分析 Botafogo SP vs CRB")
        aliases = await load_aliases(session)
        if aliases:
            query = MatchQuery(
                home=normalize_team_name(query.home, aliases),
                away=normalize_team_name(query.away, aliases),
                raw=query.raw,
            )
        fixtures = self.api.fixtures_by_date_window(datetime.now(SHANGHAI_TZ), days_before=1, days_after=3)
        candidates = rank_fixture_candidates(fixtures, query)
        if not candidates:
            fixtures = _fixtures_by_team_fallback(self.api, query)
            candidates = rank_fixture_candidates(fixtures, query)
        if not candidates:
            return PipelineResult("not_found", f"❌ API-Football 未找到比赛: {query.raw}")
        if should_return_candidates(candidates):
            return PipelineResult("candidates", format_candidate_list(candidates), candidates=candidates)
        return await self.analyze_fixture(session, candidates[0].fixture_id)

    async def analyze_fixture(self, session: AsyncSession, fixture_id: int) -> PipelineResult:
        fixture = self.api.fixture_by_id(fixture_id)
        if not fixture:
            return PipelineResult("not_found", f"❌ API-Football 未找到 fixture_id={fixture_id}")

        match = await upsert_match(session, fixture)
        odds_response = self.api.odds_by_fixture(fixture_id)
        parsed_odds = parse_api_football_odds(odds_response)
        aggregate = aggregate_1x2(parsed_odds)
        aggregates = {
            "1x2": aggregate,
            "asian_handicap": aggregate_two_way(parsed_odds, "asian_handicap"),
            "over_under": aggregate_two_way(parsed_odds, "over_under"),
        }
        prediction_response = self.api.get("/predictions", {"fixture": fixture_id}).get("response", [])
        model_probs = _estimate_model_probs(aggregate, prediction_response[0] if prediction_response else None)
        candidates = select_value_candidates(fixture_id, model_probs, aggregates)
        message = format_analysis_message(match, aggregate, candidates)

        await persist_odds_snapshots(session, fixture_id, parsed_odds)
        await persist_candidates(session, candidates)
        await persist_prediction(session, match, model_probs, message, candidates)
        await session.commit()

        return PipelineResult(
            "ok",
            message,
            fixture_id=fixture_id,
            payload={
                "match": _fixture_to_match_dict(fixture),
                "value_candidates": [item.asdict() for item in candidates],
            },
        )


async def stats_summary(session: AsyncSession) -> dict[str, Any]:
    total_predictions = (await session.execute(select(func.count(Prediction.id)))).scalar_one()
    value_predictions = (
        await session.execute(select(func.count(Prediction.id)).where(Prediction.best_pick.is_not(None)))
    ).scalar_one()
    recent = (
        await session.execute(
            select(Prediction).order_by(desc(Prediction.created_at)).limit(20)
        )
    ).scalars().all()
    return {
        "total_predictions": total_predictions,
        "value_predictions": value_predictions,
        "recent_value_rate": round(value_predictions / total_predictions, 4) if total_predictions else 0,
        "recent": [
            {
                "fixture_id": item.fixture_id,
                "best_pick": item.best_display_pick,
                "value_score": item.value_score,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in recent
        ],
    }


async def add_alias(session: AsyncSession, alias: str, api_team_name: str) -> TeamAlias:
    alias = alias.strip()
    api_team_name = api_team_name.strip()
    if not alias or not api_team_name:
        raise ValueError("alias and api_team_name are required")
    key = normalize_key(alias)
    existing = (await session.execute(select(TeamAlias).where(TeamAlias.alias_key == key))).scalar_one_or_none()
    if existing:
        existing.alias = alias
        existing.api_team_name = api_team_name
        await session.commit()
        return existing
    item = TeamAlias(alias=alias, alias_key=key, api_team_name=api_team_name)
    session.add(item)
    await session.commit()
    return item
