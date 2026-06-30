"""
API-Football 数据采集器

文档: https://www.api-football.com/documentation-v3
端点:
  GET /leagues           → 联赛列表
  GET /leagues?id=X      → 联赛详情 (含 seasons)
  GET /teams?league=X&season=Y  → 球队
  GET /standings?league=X&season=Y → 积分榜
  GET /fixtures?league=X&season=Y  → 赛程
  GET /fixtures?id=X     → 单场比赛详情 (含统计数据)
  GET /predictions?fixture=X → 预测数据
  GET /teams/statistics?league=X&team=Y&season=Z → 球队统计
  GET /fixtures/headtohead?h2h=X-Y → 历史交锋
"""

import logging
import os
from dataclasses import dataclass
from typing import Optional

from data.http_client import APIClient

logger = logging.getLogger(__name__)

API_FOOTBALL_HOST = os.getenv("API_FOOTBALL_HOST", "v3.football.api-sports.io")


@dataclass
class LeagueInfo:
    league_id: int
    name: str
    country: str
    type: str = "League"
    current_season: int = 2025
    logo_url: str = ""


@dataclass
class TeamInfo:
    team_id: int
    name: str
    country: str = ""
    logo_url: str = ""


@dataclass
class MatchInfo:
    fixture_id: int
    league_id: int
    league_name: str
    date: str  # "2026-06-29T20:00:00+00:00"
    status: str  # "FT" | "NS" | "1H" | "HT" | "2H"
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    ht_home_score: Optional[int] = None
    ht_away_score: Optional[int] = None
    venue: str = ""
    round_name: str = ""


@dataclass
class TeamStats:
    team_id: int
    team_name: str
    league_id: int
    # 进攻
    goals_for_avg: float = 0.0
    goals_against_avg: float = 0.0
    avg_shots: float = 0.0
    avg_shots_on_target: float = 0.0
    avg_possession: float = 0.0
    # 防守
    tackles_avg: float = 0.0
    interceptions_avg: float = 0.0
    fouls_avg: float = 0.0
    # 纪律
    yellow_cards_avg: float = 0.0
    red_cards_avg: float = 0.0
    # 比赛
    wins: int = 0
    draws: int = 0
    losses: int = 0
    matches_played: int = 0


# ============================================================
# 联赛映射表 (常用联赛代码 → API-Football ID)
# ============================================================
COMMON_LEAGUES = {
    "epl": 39,  # 英超
    "laliga": 140,  # 西甲
    "serie_a": 135,  # 意甲
    "bundesliga": 78,  # 德甲
    "ligue1": 61,  # 法甲
    "eredivisie": 88,  # 荷甲
    "primeira": 94,  # 葡超
    "championship": 40,  # 英冠
    "mls": 253,  # 美职联
    "jleague": 98,  # J联赛
    "champions_league": 2,  # 欧冠
    "europa_league": 3,  # 欧联
}


class ApiFootballScraper:
    """API-Football 数据采集器"""

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("API_FOOTBALL_KEY", "")
        if not key:
            raise ValueError("API-Football key 未设置，请设置环境变量 API_FOOTBALL_KEY")
        self.client = APIClient(
            base_url=f"https://{API_FOOTBALL_HOST}",
            api_key=key,
            calls_per_minute=30,  # 免费版限制
        )
        self.client.session.headers.update(
            {
                "x-apisports-key": key,
            }
        )

    # ---- 联赛 ----

    def get_leagues(self, country: Optional[str] = None) -> list[LeagueInfo]:
        """获取联赛列表"""
        params = {}
        if country:
            params["country"] = country
        data = self.client.get("/leagues", params)
        leagues = []
        for item in data.get("response", []):
            league = item.get("league", {})
            c = item.get("country", {})
            seasons = item.get("seasons", [])
            latest = max((s.get("year", 0) for s in seasons), default=2025)

            leagues.append(
                LeagueInfo(
                    league_id=league.get("id", 0),
                    name=league.get("name", ""),
                    country=c.get("name", ""),
                    type=league.get("type", "League"),
                    current_season=latest,
                    logo_url=league.get("logo", ""),
                )
            )
        return leagues

    def get_league_by_code(self, code: str) -> Optional[LeagueInfo]:
        """按简称获取联赛"""
        league_id = COMMON_LEAGUES.get(code)
        if not league_id:
            return None
        data = self.client.get("/leagues", {"id": league_id})
        for item in data.get("response", []):
            league = item.get("league", {})
            c = item.get("country", {})
            seasons = item.get("seasons", [])
            latest = max((s.get("year", 0) for s in seasons), default=2025)
            return LeagueInfo(
                league_id=league.get("id", 0),
                name=league.get("name", ""),
                country=c.get("name", ""),
                type=league.get("type", "League"),
                current_season=latest,
                logo_url=league.get("logo", ""),
            )
        return None

    # ---- 球队 ----

    def get_teams(self, league_id: int, season: int) -> list[TeamInfo]:
        """获取联赛所有球队"""
        data = self.client.get("/teams", {"league": league_id, "season": season})
        teams = []
        for item in data.get("response", []):
            t = item.get("team", {})
            teams.append(
                TeamInfo(
                    team_id=t.get("id", 0),
                    name=t.get("name", ""),
                    country=t.get("country", ""),
                    logo_url=t.get("logo", ""),
                )
            )
        return teams

    # ---- 积分榜 ----

    def get_standings(self, league_id: int, season: int) -> list[dict]:
        """获取积分榜"""
        data = self.client.get("/standings", {"league": league_id, "season": season})
        standings = []
        for item in data.get("response", []):
            league_info = item.get("league", {})
            for entry in league_info.get("standings", [[]])[0]:
                team = entry.get("team", {})
                all_stats = entry.get("all", {})
                home_stats = entry.get("home", {})
                away_stats = entry.get("away", {})
                standings.append(
                    {
                        "rank": entry.get("rank", 0),
                        "team_id": team.get("id"),
                        "team_name": team.get("name"),
                        "points": entry.get("points", 0),
                        "played": all_stats.get("played", 0),
                        "win": all_stats.get("win", 0),
                        "draw": all_stats.get("draw", 0),
                        "lose": all_stats.get("lose", 0),
                        "goals_for": all_stats.get("goals", {}).get("for", 0),
                        "goals_against": all_stats.get("goals", {}).get("against", 0),
                        "goals_for_home": home_stats.get("goals", {}).get("for", 0),
                        "goals_against_away": away_stats.get("goals", {}).get("against", 0),
                        "form": entry.get("form", ""),
                    }
                )
        return standings

    # ---- 赛程 (分页迭代) ----

    def get_fixtures(
        self,
        league_id: int,
        season: int,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        status: Optional[str] = None,  # "FT" | "NS" | "LIVE"
    ) -> list[MatchInfo]:
        """获取赛程"""
        params = {"league": league_id, "season": season}
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        if status:
            params["status"] = status

        return self._fetch_all_pages("/fixtures", params, self._parse_fixture)

    def _fetch_all_pages(self, path: str, params: dict, parser) -> list:
        """分页获取全部数据"""
        results = []
        page = 1
        while True:
            p = {**params, "page": page}
            data = self.client.get(path, p)
            items = data.get("response", [])
            if not items:
                break
            for item in items:
                parsed = parser(item)
                if parsed:
                    results.append(parsed)
            paging = data.get("paging", {})
            if page >= paging.get("total", 1):
                break
            page += 1
        return results

    def _parse_fixture(self, item: dict) -> Optional[MatchInfo]:
        """解析单场比赛"""
        f = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        goals = item.get("goals", {})
        score = item.get("score", {})

        return MatchInfo(
            fixture_id=f.get("id", 0),
            league_id=league.get("id", 0),
            league_name=league.get("name", ""),
            date=f.get("date", ""),
            status=f.get("status", {}).get("short", "NS"),
            home_team_id=teams.get("home", {}).get("id", 0),
            home_team_name=teams.get("home", {}).get("name", ""),
            away_team_id=teams.get("away", {}).get("id", 0),
            away_team_name=teams.get("away", {}).get("name", ""),
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            ht_home_score=score.get("halftime", {}).get("home"),
            ht_away_score=score.get("halftime", {}).get("away"),
            venue=f.get("venue", {}).get("name", ""),
            round_name=league.get("round", "").replace("Regular Season - ", ""),
        )

    # ---- 球队统计 ----

    def get_team_statistics(
        self,
        league_id: int,
        team_id: int,
        season: int,
    ) -> Optional[TeamStats]:
        """获取球队赛季统计数据"""
        data = self.client.get(
            "/teams/statistics",
            {
                "league": league_id,
                "team": team_id,
                "season": season,
            },
        )
        resp = data.get("response", {})
        if not resp:
            return None

        fixtures = resp.get("fixtures", {})
        goals = resp.get("goals", {})
        cards = resp.get("cards", {})

        # 按比赛数取平均
        played = fixtures.get("played", {}).get("total", 1) or 1

        return TeamStats(
            team_id=team_id,
            team_name=resp.get("team", {}).get("name", ""),
            league_id=league_id,
            goals_for_avg=goals.get("for", {}).get("total", {}).get("total", 0) / played,
            goals_against_avg=goals.get("against", {}).get("total", {}).get("total", 0) / played,
            avg_shots=resp.get("shots", {}).get("total", 0) / played if "shots" in resp else 0,
            avg_possession=float(resp.get("possession", {}).get("average", "0").rstrip("%")) / 100,
            wins=fixtures.get("wins", {}).get("total", 0),
            draws=fixtures.get("draws", {}).get("total", 0),
            losses=fixtures.get("loses", {}).get("total", 0),
            matches_played=played,
            yellow_cards_avg=cards.get("yellow", {}).get("total", 0) / played,
            red_cards_avg=cards.get("red", {}).get("total", 0) / played,
        )

    # ---- 历史交锋 ----

    def get_h2h(self, team1_id: int, team2_id: int, last_n: int = 10) -> list[MatchInfo]:
        """获取两队历史交锋"""
        data = self.client.get(
            "/fixtures/headtohead",
            {
                "h2h": f"{team1_id}-{team2_id}",
                "last": last_n,
            },
        )
        matches = []
        for item in data.get("response", []):
            m = self._parse_fixture(item)
            if m:
                matches.append(m)
        return matches

    # ---- 预测 ----

    def get_predictions(self, fixture_id: int) -> dict:
        """获取 API-Football 内置的预测数据"""
        data = self.client.get("/predictions", {"fixture": fixture_id})
        resp = data.get("response", [])
        if not resp:
            return {}

        p = resp[0]
        predictions = p.get("predictions", {})
        comparison = p.get("comparison", {})
        teams = p.get("teams", {})

        return {
            "winner": predictions.get("winner", {}).get("name"),
            "win_or_draw": predictions.get("win_or_draw"),
            "under_over": predictions.get("under_over"),
            "goals_home": predictions.get("goals", {}).get("home"),
            "goals_away": predictions.get("goals", {}).get("away"),
            "advice": predictions.get("advice"),
            "percent_home": float(predictions.get("percent", {}).get("home", "0").rstrip("%")),
            "percent_draw": float(predictions.get("percent", {}).get("draw", "0").rstrip("%")),
            "percent_away": float(predictions.get("percent", {}).get("away", "0").rstrip("%")),
            # 球队形态
            "home_form": teams.get("home", {}).get("last_5", ""),
            "away_form": teams.get("away", {}).get("last_5", ""),
            "h2h_home_wins": comparison.get("h2h", {}).get("home", 0),
            "h2h_away_wins": comparison.get("h2h", {}).get("away", 0),
        }
