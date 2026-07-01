"""Small API-Football client for the Telegram-first MVP."""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from core.config import settings

logger = logging.getLogger(__name__)


class ApiFootballClient:
    def __init__(self, api_key: str | None = None, host: str | None = None):
        self.api_key = api_key or settings.API_FOOTBALL_PRIMARY_KEY
        self.base_url = f"https://{host or settings.API_FOOTBALL_HOST}".rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "x-apisports-key": self.api_key,
                "Accept": "application/json",
                "User-Agent": "FootballQuantBot/1.0",
            }
        )
        self._last_call = 0.0

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.api_key:
            return {"errors": {"key": "API_FOOTBALL_KEYS 未配置"}, "response": []}
        elapsed = time.time() - self._last_call
        if elapsed < 0.25:
            time.sleep(0.25 - elapsed)
        self._last_call = time.time()

        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = self.session.get(url, params=params or {}, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errors"):
                logger.warning(
                    "API-Football error %s params=%s errors=%s", path, params, data["errors"]
                )
            return data
        except requests.RequestException as exc:
            logger.warning("API-Football request failed %s params=%s error=%s", path, params, exc)
            return {"errors": {"request": str(exc)}, "response": []}

    def fixtures_by_date_window(
        self,
        date_from: datetime,
        days_before: int = 1,
        days_after: int = 3,
        timezone_name: str = "Asia/Shanghai",
    ) -> list[dict[str, Any]]:
        fixtures: list[dict[str, Any]] = []
        start = date_from.date() - timedelta(days=days_before)
        end = date_from.date() + timedelta(days=days_after)
        current = start
        while current <= end:
            data = self.get("/fixtures", {"date": current.isoformat(), "timezone": timezone_name})
            fixtures.extend(data.get("response", []))
            current += timedelta(days=1)
        return fixtures

    def fixture_by_id(self, fixture_id: int) -> dict[str, Any] | None:
        response = self.get("/fixtures", {"id": fixture_id}).get("response", [])
        return response[0] if response else None

    def odds_by_fixture(self, fixture_id: int) -> list[dict[str, Any]]:
        return self.get("/odds", {"fixture": fixture_id}).get("response", [])

    def teams_by_name(self, name: str) -> list[dict[str, Any]]:
        if not name:
            return []
        return self.get("/teams", {"name": name}).get("response", [])

    def teams_search(self, query: str) -> list[dict[str, Any]]:
        if not query:
            return []
        safe_query = re.sub(r"[^A-Za-z0-9 ]+", " ", query)
        safe_query = re.sub(r"\s+", " ", safe_query).strip()
        if not safe_query:
            return []
        return self.get("/teams", {"search": safe_query}).get("response", [])

    def fixtures_by_team(
        self, team_id: int, mode: str = "next", limit: int = 20
    ) -> list[dict[str, Any]]:
        if mode not in {"next", "last"}:
            raise ValueError("mode must be 'next' or 'last'")
        return self.get(
            "/fixtures",
            {"team": team_id, mode: limit, "timezone": "Asia/Shanghai"},
        ).get("response", [])

    def upcoming_fixtures(self, days: int = 3) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        fixtures: list[dict[str, Any]] = []
        for delta in range(days):
            date_str = (now + timedelta(days=delta)).date().isoformat()
            fixtures.extend(
                self.get("/fixtures", {"date": date_str, "timezone": "Asia/Shanghai"}).get(
                    "response", []
                )
            )
        return fixtures
