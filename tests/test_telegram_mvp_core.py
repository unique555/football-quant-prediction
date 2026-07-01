from services.prediction_service import (
    _bookmaker_snapshots,
    _engine_bookmaker_name,
    _selected_candidate_fields,
)
from services.telegram_mvp.fixtures import rank_fixture_candidates, should_return_candidates
from services.telegram_mvp.names import (
    api_team_search_variants,
    clear_file_alias_cache,
    load_file_alias_team_ids,
    normalize_team_name,
    parse_match_text,
)
from services.telegram_mvp.odds import BookmakerOdds, aggregate_1x2
from services.telegram_mvp.pipeline import _best_api_team_id, _query_alias_pairs_for_fixture
from services.telegram_mvp.settlement import settle_1x2, settle_asian_handicap, settle_over_under
from services.telegram_mvp.value import ModelProbabilities, kelly_fraction, select_value_candidates


def test_parse_match_text_and_chinese_aliases():
    query = parse_match_text("博塔弗戈SP vs 雷加塔斯巴西")

    assert query is not None
    assert query.home == "Botafogo SP"
    assert query.away == "CRB"
    assert normalize_team_name("巴西雷加塔斯") == "CRB"

    national_query = parse_match_text("英格兰 vs 刚果民主共和国")
    assert national_query is not None
    assert national_query.home == "England"
    assert national_query.away == "Congo DR"

    usa_query = parse_match_text("美国 vs 波黑")
    assert usa_query is not None
    assert usa_query.home == "USA"
    assert usa_query.away == "Bosnia & Herzegovina"
    assert usa_query.raw_home == "美国"
    assert usa_query.raw_away == "波黑"
    assert normalize_team_name("美国女足") == "USA W"
    assert "Bosnia" in api_team_search_variants("波黑")

    brazil_query = parse_match_text("桑托斯 vs 累西腓体育")
    assert brazil_query is not None
    assert brazil_query.home == "Santos"
    assert brazil_query.away == "Sport Recife"


def test_generated_alias_file_can_be_loaded(tmp_path, monkeypatch):
    alias_file = tmp_path / "team_aliases.generated.json"
    alias_file.write_text(
        """
        {
          "version": 1,
          "aliases": [
            {
              "api_team_id": 12345,
              "api_team_name": "Example FC",
              "aliases": ["示例队", "示例足球队"]
            }
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setenv("TEAM_ALIAS_FILE", str(alias_file))
    clear_file_alias_cache()

    assert normalize_team_name("示例队") == "Example FC"
    assert normalize_team_name("示例足球队") == "Example FC"
    assert load_file_alias_team_ids()["示例队"] == 12345

    monkeypatch.delenv("TEAM_ALIAS_FILE")
    clear_file_alias_cache()


class FakeApiFootballClient:
    def teams_by_name(self, name):
        if name == "USA":
            return [{"team": {"id": 2384, "name": "USA", "national": True}}]
        return []

    def teams_search(self, query):
        if query == "USA":
            return [
                {"team": {"id": 1, "name": "USA MLS Next Pro", "national": False}},
                {"team": {"id": 2384, "name": "USA", "national": True}},
            ]
        return []


def test_api_team_lookup_prefers_exact_national_team():
    assert _best_api_team_id(FakeApiFootballClient(), "USA") == 2384


def test_query_alias_pairs_follow_fixture_direction():
    query = parse_match_text("美国 vs 波黑")
    fixture = {
        "teams": {
            "home": {"name": "Bosnia & Herzegovina"},
            "away": {"name": "USA"},
        }
    }

    assert query is not None
    assert _query_alias_pairs_for_fixture(query, fixture) == (
        ("美国", "USA"),
        ("波黑", "Bosnia & Herzegovina"),
    )


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


def test_prediction_service_maps_bookmakers_for_engine_weights():
    assert _engine_bookmaker_name("WilliamHill") == "william_hill"
    assert _engine_bookmaker_name("Marathonbet") == "marathon"
    assert _engine_bookmaker_name("1xBet") == "1xbet"

    snapshots = _bookmaker_snapshots(
        [
            BookmakerOdds("Pinnacle", "1x2", home=2.34, draw=3.08, away=3.48),
            BookmakerOdds("WilliamHill", "1x2", home=2.31, draw=3.12, away=3.52),
        ]
    )

    assert [item.name for item in snapshots] == ["pinnacle", "william_hill"]
    assert snapshots[0].implied_home_prob > 0


def test_prediction_service_selected_fields_from_engine_report():
    from engine.orchestrator.pipeline import FinalReport

    aggregate = aggregate_1x2(
        [
            BookmakerOdds("Pinnacle", "1x2", home=2.34, draw=3.08, away=3.48),
            BookmakerOdds("Bet365", "1x2", home=2.30, draw=3.10, away=3.50),
            BookmakerOdds("Betfair", "1x2", home=2.38, draw=3.12, away=3.45),
        ]
    )
    report = FinalReport(
        home_team="France",
        away_team="Sweden",
        recommended_direction="home",
        confidence_score=0.12,
        final_home_prob=0.52,
        final_draw_prob=0.25,
        final_away_prob=0.23,
    )

    selected = _selected_candidate_fields(report, aggregate)

    assert selected["pick"] == "home"
    assert selected["display_pick"] == "胜平负：France"
    assert selected["bookmaker"] == "Betfair"
    assert selected["ev"] > 0


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
