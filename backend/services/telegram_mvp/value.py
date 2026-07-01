"""Value candidate selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from services.telegram_mvp.odds import MarketAggregate


@dataclass
class ModelProbabilities:
    home: float
    draw: float
    away: float
    over: float = 0.0
    under: float = 0.0
    ah_home: float = 0.0
    ah_away: float = 0.0


@dataclass
class ValueCandidateDTO:
    fixture_id: int
    market: str
    pick: str
    display_pick: str
    prob: float
    odds: float
    market_prob: float
    edge: float
    ev: float
    kelly: float
    risk: str
    bookmaker_count: int
    consensus_score: int
    disagreement_index: float
    value_score: int
    selected: bool
    reason: str

    def asdict(self) -> dict:
        return asdict(self)


def kelly_fraction(prob: float, odds: float) -> float:
    if odds <= 1:
        return 0.0
    k = (prob * odds - 1) / (odds - 1)
    return max(0.0, k)


def _risk(bookmaker_count: int, consensus_score: int, disagreement_index: float) -> str:
    if bookmaker_count < 2 or consensus_score < 50 or disagreement_index > 0.12:
        return "高"
    if bookmaker_count < 4 or consensus_score < 70:
        return "中"
    return "低"


def _value_score(edge: float, ev: float, kelly: float, consensus_score: int, bookmaker_count: int, risk: str) -> int:
    base = ev * 300 + edge * 200 + kelly * 120 + consensus_score * 0.2 + min(bookmaker_count, 8) * 3
    if risk == "高":
        base -= 30
    elif risk == "中":
        base -= 10
    return max(0, min(100, round(base)))


def _candidate(
    fixture_id: int,
    aggregate: MarketAggregate,
    pick: str,
    display_pick: str,
    prob: float,
    best_side: str,
) -> ValueCandidateDTO:
    odds, bookmaker = aggregate.best_odds[best_side]
    market_prob = aggregate.no_vig_probs.get(best_side, 0.0)
    edge = prob - market_prob
    ev = prob * odds - 1
    kelly = kelly_fraction(prob, odds)
    risk = _risk(aggregate.bookmaker_count, aggregate.consensus_score, aggregate.disagreement_index)
    enough_coverage = aggregate.bookmaker_count >= 2
    selected = (
        ev > 0
        and kelly > 0
        and edge > 0
        and enough_coverage
        and aggregate.consensus_score >= 50
        and risk != "高"
        and odds > 1.01
    )
    score = _value_score(edge, ev, kelly, aggregate.consensus_score, aggregate.bookmaker_count, risk)
    return ValueCandidateDTO(
        fixture_id=fixture_id,
        market=aggregate.market,
        pick=pick,
        display_pick=display_pick,
        prob=round(prob, 4),
        odds=round(odds, 3),
        market_prob=round(market_prob, 4),
        edge=round(edge, 4),
        ev=round(ev, 4),
        kelly=round(kelly, 4),
        risk=risk,
        bookmaker_count=aggregate.bookmaker_count,
        consensus_score=aggregate.consensus_score,
        disagreement_index=aggregate.disagreement_index,
        value_score=score,
        selected=selected,
        reason=f"最高赔率 {odds:.2f} {bookmaker}; 机构{aggregate.bookmaker_count}家; 一致性{aggregate.consensus_score}",
    )


def select_value_candidates(
    fixture_id: int,
    model: ModelProbabilities,
    aggregates: dict[str, MarketAggregate | None],
) -> list[ValueCandidateDTO]:
    candidates: list[ValueCandidateDTO] = []
    one_x_two = aggregates.get("1x2")
    if one_x_two:
        mapping = {
            "home": ("home", "胜平负：主胜", model.home),
            "draw": ("draw", "胜平负：平局", model.draw),
            "away": ("away", "胜平负：客胜", model.away),
        }
        for side, (pick, display, prob) in mapping.items():
            candidates.append(_candidate(fixture_id, one_x_two, pick, display, prob, side))

    ah = aggregates.get("asian_handicap")
    if ah and model.ah_home and model.ah_away:
        line = ah.avg_odds.get("line", 0.0)
        candidates.append(_candidate(fixture_id, ah, "home", f"亚盘：主队 {line:+g}", model.ah_home, "home"))
        candidates.append(_candidate(fixture_id, ah, "away", f"亚盘：客队 {-line:+g}", model.ah_away, "away"))

    ou = aggregates.get("over_under")
    if ou and model.over and model.under:
        line = ou.avg_odds.get("line", 0.0)
        candidates.append(_candidate(fixture_id, ou, "over", f"大小球：大 {line:g}", model.over, "over"))
        candidates.append(_candidate(fixture_id, ou, "under", f"大小球：小 {line:g}", model.under, "under"))

    return sorted(candidates, key=lambda item: (item.selected, item.value_score), reverse=True)
