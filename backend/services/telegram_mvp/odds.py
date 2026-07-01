"""Odds parsing and aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Any

PREFERRED_BOOKMAKERS = [
    "Pinnacle",
    "Bet365",
    "Betfair",
    "1xBet",
    "WilliamHill",
    "Marathonbet",
    "188Bet",
    "Bwin",
    "Unibet",
    "10Bet",
]


BOOKMAKER_ALIASES = {
    "pinnacle sports": "Pinnacle",
    "pinnacle": "Pinnacle",
    "bet365": "Bet365",
    "betfair": "Betfair",
    "1xbet": "1xBet",
    "william hill": "WilliamHill",
    "williamhill": "WilliamHill",
}


@dataclass
class BookmakerOdds:
    bookmaker: str
    market: str
    home: float | None = None
    draw: float | None = None
    away: float | None = None
    line: float | None = None
    over: float | None = None
    under: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketAggregate:
    market: str
    bookmaker_count: int
    avg_odds: dict[str, float]
    no_vig_probs: dict[str, float]
    best_odds: dict[str, tuple[float, str]]
    consensus_score: int
    disagreement_index: float
    raw_bookmakers: list[BookmakerOdds]


def normalize_bookmaker(name: str) -> str:
    return BOOKMAKER_ALIASES.get((name or "").strip().lower(), (name or "").strip())


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _bet_market_name(bet: dict[str, Any]) -> str:
    text = f"{bet.get('name', '')} {bet.get('id', '')}".lower()
    if "match winner" in text or "1x2" in text or bet.get("id") == 1:
        return "1x2"
    if "asian handicap" in text or "handicap" in text:
        return "asian_handicap"
    if "goals over/under" in text or "over/under" in text or "total" in text:
        return "over_under"
    return ""


def _parse_line(value: str) -> float | None:
    if not value:
        return None
    parts = str(value).replace(",", " ").replace("(", " ").replace(")", " ").split()
    for part in reversed(parts):
        part = part.replace("+", "")
        parsed = safe_float(part)
        if parsed is not None:
            return parsed
    return None


def parse_api_football_odds(response: list[dict[str, Any]]) -> list[BookmakerOdds]:
    parsed: list[BookmakerOdds] = []
    for fixture_odds in response:
        for bookmaker in fixture_odds.get("bookmakers", []):
            bookmaker_name = normalize_bookmaker(bookmaker.get("name", ""))
            for bet in bookmaker.get("bets", []):
                market = _bet_market_name(bet)
                if not market:
                    continue
                values = bet.get("values", [])
                if market == "1x2":
                    row = BookmakerOdds(bookmaker=bookmaker_name, market=market, raw=bookmaker)
                    for value in values:
                        side = str(value.get("value", "")).strip().lower()
                        odd = safe_float(value.get("odd"))
                        if side == "home":
                            row.home = odd
                        elif side == "draw":
                            row.draw = odd
                        elif side == "away":
                            row.away = odd
                    if row.home and row.draw and row.away:
                        parsed.append(row)
                elif market == "asian_handicap":
                    home_row = away_row = None
                    for value in values:
                        side = str(value.get("value", "")).lower()
                        odd = safe_float(value.get("odd"))
                        line = _parse_line(str(value.get("value", "")))
                        if "home" in side and line is not None:
                            home_row = (line, odd)
                        elif "away" in side and line is not None:
                            away_row = (line, odd)
                    if home_row and away_row and home_row[0] == away_row[0]:
                        parsed.append(
                            BookmakerOdds(
                                bookmaker=bookmaker_name,
                                market=market,
                                line=home_row[0],
                                home=home_row[1],
                                away=away_row[1],
                                raw=bookmaker,
                            )
                        )
                elif market == "over_under":
                    over_row = under_row = None
                    for value in values:
                        side = str(value.get("value", "")).lower()
                        odd = safe_float(value.get("odd"))
                        line = _parse_line(str(value.get("value", "")))
                        if "over" in side and line is not None:
                            over_row = (line, odd)
                        elif "under" in side and line is not None:
                            under_row = (line, odd)
                    if over_row and under_row and over_row[0] == under_row[0]:
                        parsed.append(
                            BookmakerOdds(
                                bookmaker=bookmaker_name,
                                market=market,
                                line=over_row[0],
                                over=over_row[1],
                                under=under_row[1],
                                raw=bookmaker,
                            )
                        )
    return parsed


def _no_vig(odds: list[float]) -> list[float]:
    raw = [1 / odd for odd in odds if odd and odd > 1]
    total = sum(raw)
    return [x / total for x in raw] if total else []


def aggregate_1x2(bookmaker_odds: list[BookmakerOdds]) -> MarketAggregate | None:
    rows = [row for row in bookmaker_odds if row.market == "1x2" and row.home and row.draw and row.away]
    if not rows:
        return None

    home_vals = [float(row.home) for row in rows]
    draw_vals = [float(row.draw) for row in rows]
    away_vals = [float(row.away) for row in rows]
    avg_odds = {
        "home": round(mean(home_vals), 3),
        "draw": round(mean(draw_vals), 3),
        "away": round(mean(away_vals), 3),
    }
    no_vig_probs = dict(zip(("home", "draw", "away"), [round(x, 4) for x in _no_vig(list(avg_odds.values()))]))
    best_odds = {}
    for side in ("home", "draw", "away"):
        best = max(rows, key=lambda row: getattr(row, side) or 0)
        best_odds[side] = (float(getattr(best, side) or 0), best.bookmaker)

    probs_by_bookmaker = [_no_vig([float(row.home), float(row.draw), float(row.away)]) for row in rows]
    side_devs = []
    for idx in range(3):
        side_values = [prob[idx] for prob in probs_by_bookmaker if len(prob) == 3]
        if len(side_values) > 1:
            side_devs.append(pstdev(side_values))
    disagreement = round(mean(side_devs), 4) if side_devs else 0.0
    consensus = max(0, min(100, round(100 - disagreement * 450)))
    return MarketAggregate(
        market="1x2",
        bookmaker_count=len(rows),
        avg_odds=avg_odds,
        no_vig_probs=no_vig_probs,
        best_odds=best_odds,
        consensus_score=consensus,
        disagreement_index=disagreement,
        raw_bookmakers=rows,
    )


def aggregate_two_way(bookmaker_odds: list[BookmakerOdds], market: str) -> MarketAggregate | None:
    rows = [row for row in bookmaker_odds if row.market == market]
    if not rows:
        return None
    # Use the most common line to avoid mixing handicap/totals.
    line_counts: dict[float, int] = {}
    for row in rows:
        if row.line is not None:
            line_counts[row.line] = line_counts.get(row.line, 0) + 1
    if not line_counts:
        return None
    main_line = max(line_counts, key=line_counts.get)
    rows = [row for row in rows if row.line == main_line]
    if market == "asian_handicap":
        first_key, second_key = "home", "away"
    else:
        first_key, second_key = "over", "under"
    rows = [row for row in rows if getattr(row, first_key) and getattr(row, second_key)]
    if not rows:
        return None

    first_vals = [float(getattr(row, first_key)) for row in rows]
    second_vals = [float(getattr(row, second_key)) for row in rows]
    avg_odds = {
        "line": round(main_line, 3),
        first_key: round(mean(first_vals), 3),
        second_key: round(mean(second_vals), 3),
    }
    no_vig_probs = dict(zip((first_key, second_key), [round(x, 4) for x in _no_vig([avg_odds[first_key], avg_odds[second_key]])]))
    best_odds = {}
    for side in (first_key, second_key):
        best = max(rows, key=lambda row: getattr(row, side) or 0)
        best_odds[side] = (float(getattr(best, side) or 0), best.bookmaker)

    probs_by_bookmaker = [_no_vig([float(getattr(row, first_key)), float(getattr(row, second_key))]) for row in rows]
    side_devs = []
    for idx in range(2):
        side_values = [prob[idx] for prob in probs_by_bookmaker if len(prob) == 2]
        if len(side_values) > 1:
            side_devs.append(pstdev(side_values))
    disagreement = round(mean(side_devs), 4) if side_devs else 0.0
    consensus = max(0, min(100, round(100 - disagreement * 500)))
    return MarketAggregate(
        market=market,
        bookmaker_count=len(rows),
        avg_odds=avg_odds,
        no_vig_probs=no_vig_probs,
        best_odds=best_odds,
        consensus_score=consensus,
        disagreement_index=disagreement,
        raw_bookmakers=rows,
    )
