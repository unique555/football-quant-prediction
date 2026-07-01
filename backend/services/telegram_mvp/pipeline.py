"""End-to-end analysis pipeline used by Telegram, API routes, and tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import models  # noqa: F401  # Ensure foreign-key target tables are registered.
from models.match import Match
from models.prediction import Prediction
from models.telegram_mvp import FixtureAlias, OddsSnapshot, TeamAlias, ValueCandidate
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
    api_team_search_variants,
    contains_cjk,
    is_likely_national_team,
    load_file_alias_team_ids,
    normalize_key,
    normalize_team_name,
    parse_match_text,
    team_similarity,
)
from services.telegram_mvp.odds import (
    BookmakerOdds,
    MarketAggregate,
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
FIXTURE_DAYS_BEFORE = 1
FIXTURE_DAYS_AFTER = 5
FIXTURE_CACHE_TTL_DAYS = 7
ODDS_CACHE_MINUTES = 10


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
    return (
        datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )


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


async def load_alias_team_ids(session: AsyncSession) -> dict[str, int]:
    rows = (
        (await session.execute(select(TeamAlias).where(TeamAlias.api_team_id.is_not(None))))
        .scalars()
        .all()
    )
    team_ids = load_file_alias_team_ids()
    team_ids.update(
        {normalize_key(row.api_team_name): int(row.api_team_id) for row in rows if row.api_team_id}
    )
    team_ids.update(
        {normalize_key(row.alias): int(row.api_team_id) for row in rows if row.api_team_id}
    )
    return team_ids


def _team_result_score(input_name: str, team: dict[str, Any]) -> float:
    candidate_name = team.get("name", "")
    score = team_similarity(input_name, candidate_name)
    if normalize_key(input_name) == normalize_key(candidate_name):
        score += 0.15
    if is_likely_national_team(input_name) and team.get("national"):
        score += 0.12
    if is_likely_national_team(input_name) and not team.get("national"):
        score -= 0.08
    return score


def _best_api_team(api: ApiFootballClient, team_name: str) -> dict[str, Any] | None:
    best_id = None
    best_team: dict[str, Any] | None = None
    best_score = 0.0
    seen_ids: set[int] = set()
    for variant in api_team_search_variants(team_name):
        responses = [*api.teams_by_name(variant), *api.teams_search(variant)]
        for item in responses:
            team = item.get("team", {})
            team_id = team.get("id")
            if not team_id or int(team_id) in seen_ids:
                continue
            seen_ids.add(int(team_id))
            score = _team_result_score(team_name, team)
            if score > best_score:
                best_score = score
                best_id = team_id
                best_team = team
    return best_team if best_id and best_score >= 0.72 else None


def _best_api_team_id(api: ApiFootballClient, team_name: str) -> int | None:
    team = _best_api_team(api, team_name)
    return int(team["id"]) if team and team.get("id") else None


def _fixtures_by_team_fallback(
    api: ApiFootballClient,
    query: MatchQuery,
    alias_team_ids: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    alias_team_ids = alias_team_ids or {}
    team_ids = [
        team_id
        for team_id in (
            alias_team_ids.get(normalize_key(query.home)) or _best_api_team_id(api, query.home),
            alias_team_ids.get(normalize_key(query.away)) or _best_api_team_id(api, query.away),
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


def _query_alias_pairs_for_fixture(
    query: MatchQuery, fixture: dict[str, Any]
) -> tuple[tuple[str, str], ...]:
    teams = fixture.get("teams", {})
    home_name = teams.get("home", {}).get("name", "")
    away_name = teams.get("away", {}).get("name", "")
    direct = (team_similarity(query.home, home_name) + team_similarity(query.away, away_name)) / 2
    reverse = (team_similarity(query.home, away_name) + team_similarity(query.away, home_name)) / 2
    if reverse > direct:
        return ((query.raw_home, away_name), (query.raw_away, home_name))
    return ((query.raw_home, home_name), (query.raw_away, away_name))


async def remember_query_aliases(
    session: AsyncSession, query: MatchQuery, fixture: dict[str, Any]
) -> None:
    teams = fixture.get("teams", {})
    id_by_name = {
        teams.get("home", {}).get("name", ""): teams.get("home", {}).get("id"),
        teams.get("away", {}).get("name", ""): teams.get("away", {}).get("id"),
    }
    for alias, api_team_name in _query_alias_pairs_for_fixture(query, fixture):
        alias = (alias or "").strip()
        api_team_name = (api_team_name or "").strip()
        if not alias or not api_team_name or not contains_cjk(alias):
            continue
        if normalize_key(alias) == normalize_key(api_team_name):
            continue
        key = normalize_key(alias)
        existing = (
            await session.execute(select(TeamAlias).where(TeamAlias.alias_key == key))
        ).scalar_one_or_none()
        if existing:
            existing.alias = alias
            existing.api_team_name = api_team_name
            existing.api_team_id = id_by_name.get(api_team_name)
        else:
            session.add(
                TeamAlias(
                    alias=alias,
                    alias_key=key,
                    api_team_id=id_by_name.get(api_team_name),
                    api_team_name=api_team_name,
                    lang="zh",
                )
            )


def _fixture_cache_keys(query: MatchQuery) -> tuple[str, str]:
    return normalize_key(query.home), normalize_key(query.away)


async def lookup_fixture_cache(session: AsyncSession, query: MatchQuery) -> int | None:
    home_key, away_key = _fixture_cache_keys(query)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cached = (
        await session.execute(
            select(FixtureAlias)
            .where(
                FixtureAlias.home_key == home_key,
                FixtureAlias.away_key == away_key,
                FixtureAlias.expires_at > now,
            )
            .order_by(desc(FixtureAlias.updated_at))
            .limit(1)
        )
    ).scalar_one_or_none()
    return cached.fixture_id if cached else None


async def remember_fixture_cache(
    session: AsyncSession, query: MatchQuery, candidate: FixtureCandidate
) -> None:
    home_key, away_key = _fixture_cache_keys(query)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
        days=FIXTURE_CACHE_TTL_DAYS
    )
    existing = (
        await session.execute(
            select(FixtureAlias).where(
                FixtureAlias.home_key == home_key, FixtureAlias.away_key == away_key
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.home_name = candidate.home_team
        existing.away_name = candidate.away_team
        existing.fixture_id = candidate.fixture_id
        existing.source_text = query.raw
        existing.confidence = candidate.score
        existing.expires_at = expires_at
    else:
        session.add(
            FixtureAlias(
                home_key=home_key,
                away_key=away_key,
                home_name=candidate.home_team,
                away_name=candidate.away_team,
                fixture_id=candidate.fixture_id,
                source_text=query.raw,
                confidence=candidate.score,
                expires_at=expires_at,
            )
        )


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


def _estimate_model_probs(
    aggregate, api_prediction: dict[str, Any] | None = None
) -> ModelProbabilities:
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
    ah_home = max(0.0, min(1.0, probs.get("home", 0.34) + probs.get("draw", 0.32) * 0.45))
    ah_away = max(0.0, min(1.0, probs.get("away", 0.34) + probs.get("draw", 0.32) * 0.45))
    total_ah = ah_home + ah_away
    if total_ah:
        ah_home, ah_away = ah_home / total_ah, ah_away / total_ah
    over = under = 0.5
    return ModelProbabilities(
        home=float(probs.get("home", 0.34)),
        draw=float(probs.get("draw", 0.32)),
        away=float(probs.get("away", 0.34)),
        over=over,
        under=under,
        ah_home=ah_home,
        ah_away=ah_away,
    )


def _confidence_text(score: int) -> str:
    if score >= 80:
        return "高"
    if score >= 60:
        return "中"
    return "低"


def _level_text(score: int) -> str:
    if score >= 82:
        return "高"
    if score >= 70:
        return "中高"
    if score >= 55:
        return "中"
    return "偏低"


def _disagreement_text(value: float) -> str:
    if value <= 0.035:
        return "低"
    if value <= 0.07:
        return "中"
    return "高"


def _market_label(candidate: ValueCandidateDTO) -> str:
    if candidate.market == "1x2":
        return candidate.display_pick
    if candidate.market == "asian_handicap":
        return candidate.display_pick
    if candidate.market == "over_under":
        line = candidate.line if candidate.line is not None else 0
        return f"{'大球' if candidate.pick == 'over' else '小球'} {line:g}"
    return candidate.display_pick


def _format_bookmaker_1x2(aggregate: MarketAggregate | None) -> list[str]:
    if not aggregate:
        return ["暂无可用多机构欧赔"]
    rows = sorted(aggregate.raw_bookmakers, key=lambda row: row.bookmaker)[:4]
    return [f"{row.bookmaker}：{row.home:.2f} / {row.draw:.2f} / {row.away:.2f}" for row in rows]


def _format_market_summary(aggregate: MarketAggregate | None) -> list[str]:
    if not aggregate:
        return ["欧赔均值：暂无", "去水概率：暂无", "机构一致性：暂无", "赔率分歧：暂无"]
    avg = aggregate.avg_odds
    return [
        f"欧赔均值：{avg['home']:.2f} / {avg['draw']:.2f} / {avg['away']:.2f}",
        f"去水概率：主 {aggregate.no_vig_probs['home']:.1%} / "
        f"平 {aggregate.no_vig_probs['draw']:.1%} / 客 {aggregate.no_vig_probs['away']:.1%}",
        f"机构一致性：{_level_text(aggregate.consensus_score)}",
        f"赔率分歧：{_disagreement_text(aggregate.disagreement_index)}",
    ]


def _format_asian_summary(aggregate: MarketAggregate | None) -> list[str]:
    if not aggregate:
        return ["暂无可用亚盘盘口"]
    line = aggregate.avg_odds.get("line", 0.0)
    home_best = aggregate.best_odds.get("home", (0, "-"))
    return [
        f"主队 {line:+g}",
        f"最高水位：{home_best[0]:.2f} {home_best[1]}",
        f"盘口一致性：{_level_text(aggregate.consensus_score)}",
    ]


def _value_conclusion(best: ValueCandidateDTO) -> str:
    if best.market == "asian_handicap":
        return f"多机构盘口基本支持主队方向，{best.display_pick} 比直接胜平负更具价值。"
    if best.market == "over_under":
        if best.pick == "under":
            return "本场节奏预期偏慢，比分集中在 0:0 / 1:0 / 1:1。胜平负方向分歧较大，小球方向价值更高。"
        return "本场节奏预期偏快，进球预期偏高，大小球方向比胜平负更具价值。"
    return "模型概率与市场价格存在正差，欧赔与盘口方向基本一致。建议控制风险。"


def _no_value_reasons(
    candidates: list[ValueCandidateDTO], aggregates: dict[str, MarketAggregate | None]
) -> list[str]:
    reasons: list[str] = []
    if not aggregates.get("1x2"):
        reasons.append("胜平负多机构赔率不足")
    elif all(item.market != "1x2" or item.ev <= 0 for item in candidates):
        reasons.append("胜平负 EV 不足")
    if not aggregates.get("asian_handicap"):
        reasons.append("亚盘数据不足")
    elif all(item.market != "asian_handicap" or item.edge <= 0 for item in candidates):
        reasons.append("亚盘赢盘概率接近市场预期")
    if not aggregates.get("over_under"):
        reasons.append("大小球数据不足")
    elif any(item.market == "over_under" and item.is_shadow for item in candidates):
        reasons.append("大小球方向不稳定")
    if any(item.disagreement_index > 0.07 for item in candidates):
        reasons.append("多机构赔率分歧较大")
    if any(item.risk == "高" for item in candidates):
        reasons.append("风险等级偏高")
    return reasons[:5] or ["EV/Kelly/Edge/机构一致性未同时达标"]


def format_analysis_message(
    match: Match,
    aggregates: dict[str, MarketAggregate | None],
    candidates: list[ValueCandidateDTO],
) -> str:
    selected = [item for item in candidates if item.selected]
    best = selected[0] if selected else None
    kickoff = (
        match.match_date.replace(tzinfo=timezone.utc)
        .astimezone(SHANGHAI_TZ)
        .strftime("%Y-%m-%d %H:%M")
    )
    one_x_two = aggregates.get("1x2")
    ah = aggregates.get("asian_handicap")
    lines = [
        f"📊 {match.home_team_name} vs {match.away_team_name}",
        f"⏰ {kickoff}",
        "",
        "📈 多机构欧赔：",
        *_format_bookmaker_1x2(one_x_two),
        "",
        "📊 市场均值：",
        *_format_market_summary(one_x_two),
        "",
        "⚽ 亚盘主流：",
        *_format_asian_summary(ah),
        "",
    ]
    if best:
        lines.extend(
            [
                "🎯 最优价值方向",
                _market_label(best),
                "",
                "💰 投资价值",
                f"模型概率：{best.prob:.1%}",
                f"市场均值概率：{best.market_prob:.1%}",
                f"Edge：{best.edge:+.1%}",
                f"最高赔率：{best.odds:.2f} {best.best_bookmaker or ''}".strip(),
                f"EV：{best.ev:+.1%}",
                f"Kelly：{best.kelly:.3f}",
                f"价值评分：{best.value_score}%",
                "",
                f"📌 {'亚盘结论' if best.market == 'asian_handicap' else '结论'}：",
                _value_conclusion(best),
                "",
                f"⚠️ 风险：{best.risk}",
                "",
                "✅ 结论：",
                f"谨慎参考：{_market_label(best)}",
            ]
        )
    else:
        lines.extend(
            [
                "🎯 最优价值方向",
                "暂无",
                "",
                "⚠️ 结论",
                "本场没有明显正期望方向，建议观望。",
                "",
                "原因：",
            ]
        )
        for idx, reason in enumerate(_no_value_reasons(candidates, aggregates), 1):
            lines.append(f"{idx}. {reason}")
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


async def load_recent_odds_snapshots(
    session: AsyncSession,
    fixture_id: int,
    max_age_minutes: int = ODDS_CACHE_MINUTES,
) -> list[BookmakerOdds]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=max_age_minutes)
    rows = (
        (
            await session.execute(
                select(OddsSnapshot)
                .where(OddsSnapshot.fixture_id == fixture_id, OddsSnapshot.captured_at >= cutoff)
                .order_by(desc(OddsSnapshot.captured_at))
            )
        )
        .scalars()
        .all()
    )
    parsed: list[BookmakerOdds] = []
    for row in rows:
        parsed.append(
            BookmakerOdds(
                bookmaker=row.bookmaker or "",
                market=row.market,
                home=row.home_odds if row.market == "1x2" else row.ah_home_odds,
                draw=row.draw_odds,
                away=row.away_odds if row.market == "1x2" else row.ah_away_odds,
                line=row.ah_line if row.market == "asian_handicap" else row.ou_line,
                over=row.over_odds,
                under=row.under_odds,
                raw=row.raw_json or {},
            )
        )
    return parsed


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
            best_line=selected.line if selected else None,
            best_bookmaker=selected.best_bookmaker if selected else None,
            best_odds=selected.odds if selected else None,
            best_ev=selected.ev if selected else None,
            best_kelly=selected.kelly if selected else None,
            best_edge=selected.edge if selected else None,
            market_prob=selected.market_prob if selected else None,
            value_score=selected.value_score if selected else 0,
            confidence_text=_confidence_text(selected.value_score) if selected else "低",
            risk=selected.risk if selected else "中",
            settled_status="pending",
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
        alias_team_ids = await load_alias_team_ids(session)
        if aliases:
            query = MatchQuery(
                home=normalize_team_name(query.home, aliases),
                away=normalize_team_name(query.away, aliases),
                raw=query.raw,
                raw_home=query.raw_home,
                raw_away=query.raw_away,
            )
        cached_fixture_id = await lookup_fixture_cache(session, query)
        if cached_fixture_id:
            return await self.analyze_fixture(session, cached_fixture_id, source_query=query)

        fixtures = self.api.fixtures_by_date_window(
            datetime.now(SHANGHAI_TZ),
            days_before=FIXTURE_DAYS_BEFORE,
            days_after=FIXTURE_DAYS_AFTER,
        )
        candidates = rank_fixture_candidates(fixtures, query)
        if not candidates:
            fixtures = _fixtures_by_team_fallback(self.api, query, alias_team_ids)
            candidates = rank_fixture_candidates(fixtures, query)
        if not candidates:
            return PipelineResult("not_found", f"❌ API-Football 未找到比赛: {query.raw}")
        if should_return_candidates(candidates):
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
            odds_response = self.api.odds_by_fixture(fixture_id)
            parsed_odds = parse_api_football_odds(odds_response)
            fetched_fresh = True
        aggregate = aggregate_1x2(parsed_odds)
        aggregates = {
            "1x2": aggregate,
            "asian_handicap": aggregate_two_way(parsed_odds, "asian_handicap"),
            "over_under": aggregate_two_way(parsed_odds, "over_under"),
        }
        prediction_response = self.api.get("/predictions", {"fixture": fixture_id}).get(
            "response", []
        )
        model_probs = _estimate_model_probs(
            aggregate, prediction_response[0] if prediction_response else None
        )
        candidates = select_value_candidates(fixture_id, model_probs, aggregates)
        message = format_analysis_message(match, aggregates, candidates)

        if fetched_fresh:
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
        await session.execute(
            select(func.count(Prediction.id)).where(Prediction.best_pick.is_not(None))
        )
    ).scalar_one()
    recent = (
        (await session.execute(select(Prediction).order_by(desc(Prediction.created_at)).limit(20)))
        .scalars()
        .all()
    )
    return {
        "total_predictions": total_predictions,
        "value_predictions": value_predictions,
        "settled_predictions": (
            await session.execute(
                select(func.count(Prediction.id)).where(Prediction.settled_status != "pending")
            )
        ).scalar_one(),
        "recent_value_rate": round(value_predictions / total_predictions, 4)
        if total_predictions
        else 0,
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


def _bucket_bookmakers(count: int | None) -> str:
    if not count:
        return "unknown"
    if count <= 2:
        return "2家"
    if count <= 4:
        return "3-4家"
    return "5+家"


def _bucket_consensus(score: int | None) -> str:
    if score is None:
        return "unknown"
    if score < 50:
        return "<50"
    if score < 70:
        return "50-69"
    if score < 85:
        return "70-84"
    return "85+"


def _bucket_disagreement(value: float | None) -> str:
    if value is None:
        return "unknown"
    if value <= 0.035:
        return "低"
    if value <= 0.07:
        return "中"
    return "高"


def _hit(status: str | None) -> bool:
    return status in {"win", "half_win"}


async def performance_summary(session: AsyncSession) -> dict[str, Any]:
    candidates = (
        (await session.execute(select(ValueCandidate).where(ValueCandidate.selected.is_(True))))
        .scalars()
        .all()
    )
    settled = [
        item for item in candidates if item.settled_status and item.settled_status != "pending"
    ]

    def summarize(rows: list[ValueCandidate]) -> dict[str, Any]:
        if not rows:
            return {"count": 0, "hit_rate": 0.0, "profit_units": 0.0}
        hits = sum(1 for row in rows if _hit(row.settled_status))
        profit = sum(float(row.profit_units or 0) for row in rows)
        return {
            "count": len(rows),
            "hit_rate": round(hits / len(rows), 4),
            "profit_units": round(profit, 3),
        }

    def group_by(key_func) -> dict[str, Any]:
        groups: dict[str, list[ValueCandidate]] = {}
        for row in settled:
            groups.setdefault(key_func(row), []).append(row)
        return {key: summarize(rows) for key, rows in groups.items()}

    return {
        "overall": summarize(settled),
        "by_market": group_by(lambda row: row.market),
        "by_bookmaker_count": group_by(lambda row: _bucket_bookmakers(row.bookmaker_count)),
        "by_consensus": group_by(lambda row: _bucket_consensus(row.consensus_score)),
        "by_disagreement": group_by(lambda row: _bucket_disagreement(row.disagreement_index)),
        "recommendations": review_recommendations(settled),
    }


def review_recommendations(rows: list[ValueCandidate]) -> list[str]:
    if len(rows) < 10:
        return ["样本量不足，暂不自动调整评分权重。"]
    recs: list[str] = []
    high_disagreement = [row for row in rows if (row.disagreement_index or 0) > 0.07]
    if high_disagreement:
        hit_rate = sum(1 for row in high_disagreement if _hit(row.settled_status)) / len(
            high_disagreement
        )
        if hit_rate < 0.45:
            recs.append("高分歧区间表现偏弱，建议提高分歧扣分或降低推荐优先级。")
    low_consensus = [row for row in rows if (row.consensus_score or 0) < 70]
    if low_consensus:
        hit_rate = sum(1 for row in low_consensus if _hit(row.settled_status)) / len(low_consensus)
        if hit_rate < 0.45:
            recs.append("低一致性候选表现偏弱，建议提高最低一致性阈值。")
    if not recs:
        recs.append("当前评分权重暂无明显异常，保持观察。")
    return recs


async def add_alias(session: AsyncSession, alias: str, api_team_name: str) -> TeamAlias:
    alias = alias.strip()
    api_team_name = api_team_name.strip()
    if not alias or not api_team_name:
        raise ValueError("alias and api_team_name are required")
    key = normalize_key(alias)
    existing = (
        await session.execute(select(TeamAlias).where(TeamAlias.alias_key == key))
    ).scalar_one_or_none()
    if existing:
        existing.alias = alias
        existing.api_team_name = api_team_name
        await session.commit()
        return existing
    item = TeamAlias(alias=alias, alias_key=key, api_team_name=api_team_name)
    session.add(item)
    await session.commit()
    return item
