"""Odds parsing, filtering, and market aggregation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import mean, median, pstdev
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
    "marathon": "Marathonbet",
    "marathon bet": "Marathonbet",
    "188bet": "188Bet",
    "bwin": "Bwin",
    "unibet": "Unibet",
    "10bet": "10Bet",
}

MIN_ODDS = 1.01
MAX_ODDS = 80.0


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
    return_rate: float = 0.0
    overround: float = 0.0
    data_quality_score: int = 0
    excluded_bookmakers: list[str] = field(default_factory=list)


def normalize_bookmaker(name: str) -> str:
    cleaned = (name or "").strip()
    return BOOKMAKER_ALIASES.get(cleaned.lower(), cleaned)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed < MIN_ODDS or parsed > MAX_ODDS:
        return None
    return parsed


def safe_line_float(value: Any) -> float | None:
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
    text = str(value).replace(",", " ")
    matches = re.findall(r"[+-]?\d+(?:\.\d+)?", text)
    for match in reversed(matches):
        parsed = safe_line_float(match.replace("+", ""))
        if parsed is not None:
            return parsed
    return None


def parse_api_football_odds(response: list[dict[str, Any]]) -> list[BookmakerOdds]:
    parsed: list[BookmakerOdds] = []
    for fixture_odds in response:
        # API-Football v3: 每个 response 元素含 bookmaker(单数对象) + bets(数组)
        # 兼容两种结构：bookmaker(单数) 和 bookmakers(复数数组)
        bookmakers_data = fixture_odds.get("bookmakers")
        if bookmakers_data is None:
            single = fixture_odds.get("bookmaker")
            if single:
                # 把外层 bets 注入到 bookmaker 对象中，统一后续处理
                bm_with_bets = dict(single)
                bm_with_bets["bets"] = fixture_odds.get("bets", [])
                bookmakers_data = [bm_with_bets]
            else:
                continue
        for bookmaker in bookmakers_data:
            bookmaker_name = normalize_bookmaker(bookmaker.get("name", ""))
            if not bookmaker_name:
                continue
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
                        if odd is None or line is None:
                            continue
                        if "home" in side:
                            home_row = (line, odd)
                        elif "away" in side:
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
                        if odd is None or line is None:
                            continue
                        if "over" in side:
                            over_row = (line, odd)
                        elif "under" in side:
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


def no_vig_probs(odds: list[float]) -> list[float]:
    raw = [1 / odd for odd in odds if odd and odd > 1]
    total = sum(raw)
    return [x / total for x in raw] if total else []


def return_rate(odds: list[float]) -> float:
    implied = sum(1 / odd for odd in odds if odd and odd > 1)
    return round(1 / implied, 4) if implied else 0.0


def _bookmaker_rank(name: str) -> int:
    try:
        return PREFERRED_BOOKMAKERS.index(name)
    except ValueError:
        return len(PREFERRED_BOOKMAKERS) + 10


def _dedupe_bookmakers(rows: list[BookmakerOdds]) -> list[BookmakerOdds]:
    seen: dict[str, BookmakerOdds] = {}
    for row in sorted(rows, key=lambda item: _bookmaker_rank(item.bookmaker)):
        seen.setdefault(row.bookmaker, row)
    return list(seen.values())


def _is_low_quality(row: BookmakerOdds) -> bool:
    return row.bookmaker not in PREFERRED_BOOKMAKERS and not row.bookmaker


def _filter_outliers(
    rows: list[BookmakerOdds], sides: tuple[str, ...]
) -> tuple[list[BookmakerOdds], list[str]]:
    rows = [row for row in _dedupe_bookmakers(rows) if not _is_low_quality(row)]
    excluded: list[str] = []
    if len(rows) < 4:
        return rows, excluded

    medians = {side: median(float(getattr(row, side)) for row in rows) for side in sides}
    kept: list[BookmakerOdds] = []
    for row in rows:
        outlier = False
        for side in sides:
            value = float(getattr(row, side))
            center = medians[side]
            if center and abs(value - center) / center > 0.45:
                outlier = True
                break
        if outlier:
            excluded.append(row.bookmaker)
        else:
            kept.append(row)
    return (kept or rows), excluded


def _consensus(rows: list[BookmakerOdds], sides: tuple[str, ...]) -> tuple[int, float]:
    probs_by_bookmaker = [
        no_vig_probs([float(getattr(row, side)) for side in sides]) for row in rows
    ]
    side_devs = []
    for idx in range(len(sides)):
        side_values = [prob[idx] for prob in probs_by_bookmaker if len(prob) == len(sides)]
        if len(side_values) > 1:
            side_devs.append(pstdev(side_values))
    disagreement = round(mean(side_devs), 4) if side_devs else 0.0
    multiplier = 450 if len(sides) == 3 else 500
    return max(0, min(100, round(100 - disagreement * multiplier))), disagreement


def _quality_score(rows: list[BookmakerOdds], consensus_score: int, excluded_count: int) -> int:
    coverage = min(len(rows), 8) / 8
    preferred = sum(1 for row in rows if row.bookmaker in PREFERRED_BOOKMAKERS)
    preferred_score = min(preferred, 5) / 5
    penalty = min(excluded_count, 5) * 4
    return max(
        0, min(100, round(coverage * 45 + preferred_score * 25 + consensus_score * 0.3 - penalty))
    )


def _aggregate(
    rows: list[BookmakerOdds], market: str, sides: tuple[str, ...]
) -> MarketAggregate | None:
    rows = [row for row in rows if all(getattr(row, side) for side in sides)]
    rows, excluded = _filter_outliers(rows, sides)
    if not rows:
        return None
    avg_odds = {side: round(mean(float(getattr(row, side)) for row in rows), 3) for side in sides}
    if "line" in rows[0].__dict__ and rows[0].line is not None:
        avg_odds["line"] = round(float(rows[0].line), 3)
    probs = no_vig_probs([avg_odds[side] for side in sides])
    no_vig = dict(zip(sides, [round(x, 4) for x in probs]))
    best_odds = {}
    for side in sides:
        best = max(rows, key=lambda row: getattr(row, side) or 0)
        best_odds[side] = (float(getattr(best, side) or 0), best.bookmaker)
    consensus_score, disagreement = _consensus(rows, sides)
    rr = return_rate([avg_odds[side] for side in sides])
    return MarketAggregate(
        market=market,
        bookmaker_count=len(rows),
        avg_odds=avg_odds,
        no_vig_probs=no_vig,
        best_odds=best_odds,
        consensus_score=consensus_score,
        disagreement_index=disagreement,
        raw_bookmakers=rows,
        return_rate=rr,
        overround=round((1 / rr) - 1, 4) if rr else 0.0,
        data_quality_score=_quality_score(rows, consensus_score, len(excluded)),
        excluded_bookmakers=excluded,
    )


def aggregate_1x2(bookmaker_odds: list[BookmakerOdds]) -> MarketAggregate | None:
    rows = [
        row for row in bookmaker_odds if row.market == "1x2" and row.home and row.draw and row.away
    ]
    return _aggregate(rows, "1x2", ("home", "draw", "away"))


def aggregate_two_way(bookmaker_odds: list[BookmakerOdds], market: str) -> MarketAggregate | None:
    rows = [row for row in bookmaker_odds if row.market == market and row.line is not None]
    if not rows:
        return None
    line_counts: dict[float, int] = {}
    for row in rows:
        line_counts[float(row.line)] = line_counts.get(float(row.line), 0) + 1
    main_line = max(line_counts, key=line_counts.get)
    rows = [row for row in rows if row.line == main_line]
    sides = ("home", "away") if market == "asian_handicap" else ("over", "under")
    return _aggregate(rows, market, sides)
