"""
数据服务 — 联赛、球队、比赛数据查询
→ 待实现
"""


class DataService:
    """数据查询服务"""

    def get_leagues(self) -> list:
        raise NotImplementedError

    def get_standings(self, league_id: int) -> list:
        raise NotImplementedError

    def get_teams(self, league_id: int) -> list:
        raise NotImplementedError

    def get_matches(self, league_id: int, date_range: tuple) -> list:
        raise NotImplementedError
