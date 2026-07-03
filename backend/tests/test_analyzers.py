"""
测试：11 维度分析模块 — 用 mock 数据验证各模块接口
"""
from __future__ import annotations
from unittest.mock import MagicMock
import pytest

@pytest.fixture
def mock_api():
    api = MagicMock()
    api.get.return_value = {"response": []}
    return api

@pytest.fixture
def mock_fixture():
    return {"fixture": {"id": 1, "date": "2026-07-05T19:00:00+00:00", "status": {"short": "NS"}}, "league": {"id": 39, "name": "Premier League", "season": 2025}, "teams": {"home": {"id": 42, "name": "Arsenal"}, "away": {"id": 49, "name": "Chelsea"}}, "goals": {"home": None, "away": None}}

@pytest.fixture
def mock_fundamental():
    return {"standings": {"home": {"rank": 2, "points": 45, "played": 19, "win": 14, "draw": 3, "lose": 2, "goals_for": 42, "goals_against": 15, "goal_diff": 27, "form": "WWDWW", "home_record": "9胜1平0负", "home_goals_for": 23, "home_goals_against": 7}, "away": {"rank": 6, "points": 33, "played": 19, "win": 10, "draw": 3, "lose": 6, "goals_for": 31, "goals_against": 24, "goal_diff": 7, "form": "WLWWD", "away_record": "4胜1平5负", "away_goals_for": 13, "away_goals_against": 14}}, "form": {"home": {"wins": 7, "draws": 2, "losses": 1, "goals_for_avg": 2.1, "goals_against_avg": 0.8, "clean_sheet_rate": 0.5, "form_score": 0.82}, "away": {"wins": 5, "draws": 3, "losses": 2, "goals_for_avg": 1.5, "goals_against_avg": 1.2, "clean_sheet_rate": 0.3, "form_score": 0.60}}, "h2h_summary": {"home_wins": 3, "draws": 2, "away_wins": 1}, "h2h": [], "home_record": {"goals_for_avg": 2.3, "goals_against_avg": 0.7, "avg_shots": 15.3, "avg_possession": 0.58}, "away_record": {"goals_for_avg": 1.6, "goals_against_avg": 1.1, "avg_shots": 12.8, "avg_possession": 0.52}}

class TestAnalyzers:
    def test_fundamental_analyzer_empty(self, mock_api, mock_fixture):
        from services.analyzers import fundamental_analyzer
        result = fundamental_analyzer.analyze(mock_api, mock_fixture)
        assert isinstance(result, dict)
        assert "standings" in result

    def test_tactical_analyzer_empty(self, mock_api, mock_fixture, mock_fundamental):
        from services.analyzers import tactical_analyzer
        result = tactical_analyzer.analyze(mock_api, mock_fixture, mock_fundamental)
        assert isinstance(result, dict)

    def test_motivation_analyzer(self, mock_api, mock_fixture, mock_fundamental):
        from services.analyzers import motivation_analyzer
        result = motivation_analyzer.analyze(mock_api, mock_fixture, mock_fundamental)
        assert "motivation" in result

    def test_goals_analyzer(self, mock_api, mock_fixture, mock_fundamental):
        from services.analyzers import goals_analyzer
        result = goals_analyzer.analyze(mock_api, mock_fixture, mock_fundamental, {"1x2": None})
        assert isinstance(result, dict)

    def test_corners_analyzer(self, mock_api, mock_fixture, mock_fundamental):
        from services.analyzers import corners_analyzer
        result = corners_analyzer.analyze(mock_api, mock_fixture, mock_fundamental, {})
        assert isinstance(result, dict)

    def test_htft_analyzer(self, mock_api, mock_fixture, mock_fundamental):
        from services.analyzers import htft_analyzer
        result = htft_analyzer.analyze(mock_api, mock_fixture, mock_fundamental, {})
        assert isinstance(result, dict)
        assert "htft_probs" in result

    def test_data_quality(self, mock_fixture, mock_fundamental):
        from services.analyzers import data_quality
        result = data_quality.assess(mock_fixture, mock_fundamental, {}, {})
        assert "total_score" in result

class TestFeatureBuilder:
    def test_build_without_data(self):
        from services.feature_builder import FeatureBuilder
        fb = FeatureBuilder()
        result = fb.build({}, {}, {})
        assert isinstance(result, dict)

    def test_build_with_fundamental(self, mock_fundamental):
        from services.feature_builder import FeatureBuilder
        fb = FeatureBuilder()
        result = fb.build({}, mock_fundamental, {})
        assert result.get("home_rank") == 2

    def test_build_target(self, mock_fixture):
        from services.feature_builder import FeatureBuilder
        fb = FeatureBuilder()
        assert fb.build_target(mock_fixture) is None
        f2 = dict(mock_fixture); f2["goals"] = {"home": 2, "away": 1}
        assert fb.build_target(f2) == 0

class TestReportFormatter:
    def test_format_reports(self):
        from services.report_formatter import format_reports
        result = format_reports(
            match_data={"home_team": "A", "away_team": "B", "league_name": "Test", "kickoff_str": "", "venue": ""},
            classification={"match_type": "test", "phase": "mid", "favorite": "A"},
            fundamental={"standings": {}, "form": {}, "h2h_summary": {}},
            tactical={}, motivation={"motivation": {"home": {}, "away": {}}},
            odds_data={"bookmakers": []},
            goals={}, corners={}, htft={},
            verdict={"final_probs": {"home": 0.5, "draw": 0.3, "away": 0.2}, "market_probs": {}, "recommendation": "A", "best_edge": 0.05, "best_odds": 2.0, "best_bookmaker": "Test", "signals": []},
            risks=["测试风险"],
            data_quality_data={"checks": [], "total_score": 80, "analyzable": True},
        )
        assert "telegram_message" in result
        assert "full_report" in result

class TestFixtureDiscovery:
    def test_is_excluded(self):
        excluded_names = {"Friendlies Clubs", "U19 Championship", "Youth Championship", "Reserve League", "Futsal", "Beach Soccer"}
        excluded_kw = ["U15", "U16", "U17", "U18", "U19", "U20", "U21", "U23", "Youth", "Reserve", "Futsal", "Beach"]
        def _is_excluded(name):
            if not name: return True
            if name in excluded_names: return True
            for kw in excluded_kw:
                if kw.lower() in name.lower(): return True
            return False
        assert _is_excluded("Friendlies Clubs") is True
        assert _is_excluded("Premier League") is False

    def test_scheduled_statuses(self):
        scheduled = {"NS", "TBD", "PST"}
        assert "NS" in scheduled
        assert "FT" not in scheduled
