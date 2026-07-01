from services.telegram_mvp.fixtures import rank_fixture_candidates, should_return_candidates
from services.telegram_mvp.names import normalize_team_name, parse_match_text
from services.telegram_mvp.odds import BookmakerOdds, aggregate_1x2
from services.telegram_mvp.settlement import settle_1x2, settle_asian_handicap, settle_over_under
from services.telegram_mvp.value import ModelProbabilities, kelly_fraction, select_value_candidates


def test_parse_match_text_and_chinese_aliases():
    query = parse_match_text("博塔弗戈SP vs 雷加塔斯巴西")

    assert query is not None
    assert query.home == "Botafogo SP"
    assert query.away == "CRB"
    assert normalize_team_name("巴西雷加塔斯") == "CRB"


def test_fixture_candidate_selection_prefers_close_match():
    query = parse_match_text("Botafogo SP vs CRB")
    fixtures = [
        {
            "fixture": {"id": 1, "date": "2026-07-01T07:00:00+00:00", "status": {"short": "NS"}},
            "teams": {"home": {"name": "Botafogo SP"}, "away": {"name": "CRB"}},
            "league": {"name": "Serie B", "season": 2026},
        },
        {
            "fixture": {"id": 2, "date": "2026-07-03T07:00:00+00:00", "status": {"short": "NS"}},
            "teams": {"home": {"name": "Botafogo RJ"}, "away": {"name": "CRB"}},
            "league": {"name": "Cup", "season": 2026},
        },
    ]

    candidates = rank_fixture_candidates(fixtures, query)

    assert candidates[0].fixture_id == 1
    assert should_return_candidates(candidates) is False


def test_aggregate_1x2_computes_consensus_and_best_odds():
    aggregate = aggregate_1x2(
        [
            BookmakerOdds("Pinnacle", "1x2", home=2.34, draw=3.08, away=3.48),
            BookmakerOdds("Bet365", "1x2", home=2.30, draw=3.10, away=3.50),
            BookmakerOdds("Betfair", "1x2", home=2.38, draw=3.12, away=3.45),
        ]
    )

    assert aggregate is not None
    assert aggregate.bookmaker_count == 3
    assert aggregate.best_odds["home"] == (2.38, "Betfair")
    assert aggregate.consensus_score > 80


def test_value_candidate_requires_positive_ev_kelly_edge_and_coverage():
    aggregate = aggregate_1x2(
        [
            BookmakerOdds("Pinnacle", "1x2", home=2.34, draw=3.08, away=3.48),
            BookmakerOdds("Bet365", "1x2", home=2.30, draw=3.10, away=3.50),
            BookmakerOdds("Betfair", "1x2", home=2.38, draw=3.12, away=3.45),
        ]
    )
    candidates = select_value_candidates(
        100,
        ModelProbabilities(home=0.46, draw=0.28, away=0.26),
        {"1x2": aggregate, "asian_handicap": None, "over_under": None},
    )

    assert candidates[0].selected is True
    assert candidates[0].pick == "home"
    assert candidates[0].ev > 0
    assert kelly_fraction(candidates[0].prob, candidates[0].odds) > 0


def test_no_value_candidate_when_single_bookmaker():
    aggregate = aggregate_1x2([BookmakerOdds("Pinnacle", "1x2", home=2.34, draw=3.08, away=3.48)])
    candidates = select_value_candidates(
        100,
        ModelProbabilities(home=0.46, draw=0.28, away=0.26),
        {"1x2": aggregate, "asian_handicap": None, "over_under": None},
    )

    assert all(candidate.selected is False for candidate in candidates)


def test_settlement_helpers():
    assert settle_1x2(1, 0, "home") == "win"
    assert settle_1x2(1, 0, "away") == "loss"
    assert settle_over_under(2, 1, 2.5, "over") == "win"
    assert settle_over_under(1, 1, 2.0, "under") == "push"
    assert settle_asian_handicap(1, 0, -0.25, "home") in {"half_win", "win"}
    assert settle_asian_handicap(0, 0, -0.5, "home") == "loss"
