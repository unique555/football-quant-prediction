"""Build local team alias files for Chinese input recognition."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from services.telegram_mvp.api_football import ApiFootballClient
from services.telegram_mvp.names import contains_cjk, normalize_key, team_similarity

logger = logging.getLogger(__name__)
WIKIDATA_API = "https://www.wikidata.org/w/api.php"


@dataclass
class TeamAliasRecord:
    api_team_id: int
    api_team_name: str
    country: str = ""
    national: bool = False
    aliases: set[str] = field(default_factory=set)
    source: str = "api-football+wikidata"

    def asdict(self) -> dict[str, Any]:
        aliases = sorted(
            {
                alias.strip()
                for alias in self.aliases
                if alias and contains_cjk(alias) and normalize_key(alias) != normalize_key(self.api_team_name)
            },
            key=lambda item: (len(item), item),
        )
        return {
            "api_team_id": self.api_team_id,
            "api_team_name": self.api_team_name,
            "country": self.country,
            "national": self.national,
            "aliases": aliases,
            "source": self.source,
        }


class WikidataAliasClient:
    def __init__(self, min_delay: float = 0.5):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "FootballQuantBot/1.0 (team alias builder)"})
        self.min_delay = min_delay
        self._last_call = 0.0
        self._entity_cache: dict[str, dict[str, Any]] = {}

    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(3):
            elapsed = time.time() - self._last_call
            if elapsed < self.min_delay:
                time.sleep(self.min_delay - elapsed)
            self._last_call = time.time()
            try:
                response = self.session.get(WIKIDATA_API, params=params, timeout=20)
                if response.status_code == 429 and attempt < 2:
                    retry_after = int(response.headers.get("Retry-After", "3"))
                    time.sleep(max(retry_after, 3))
                    continue
                response.raise_for_status()
                return response.json()
            except requests.RequestException as exc:
                if attempt < 2:
                    time.sleep(2 + attempt)
                    continue
                logger.warning("Wikidata request failed params=%s error=%s", params, exc)
        return {}

    def search_entities(self, name: str, limit: int = 5) -> list[str]:
        data = self.get(
            {
                "action": "wbsearchentities",
                "format": "json",
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": limit,
                "search": name,
            }
        )
        return [item["id"] for item in data.get("search", []) if item.get("id")]

    def entity(self, entity_id: str) -> dict[str, Any]:
        if entity_id in self._entity_cache:
            return self._entity_cache[entity_id]
        data = self.get(
            {
                "action": "wbgetentities",
                "format": "json",
                "ids": entity_id,
                "props": "labels|aliases|descriptions",
                "languages": "en|zh|zh-hans|zh-hant|zh-cn|zh-tw|zh-hk",
                "languagefallback": 1,
            }
        )
        entity = data.get("entities", {}).get(entity_id, {})
        self._entity_cache[entity_id] = entity
        return entity

    def chinese_aliases_for_team(self, api_team_name: str) -> set[str]:
        aliases: set[str] = set()
        for entity_id in self.search_entities(api_team_name):
            entity = self.entity(entity_id)
            english_label = (entity.get("labels", {}).get("en", {}) or {}).get("value", "")
            if english_label and team_similarity(api_team_name, english_label) < 0.72:
                continue
            labels = entity.get("labels", {})
            for lang in ("zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw", "zh-hk"):
                value = (labels.get(lang, {}) or {}).get("value", "")
                if value and contains_cjk(value):
                    aliases.add(value)
            for lang, values in (entity.get("aliases") or {}).items():
                if not lang.startswith("zh"):
                    continue
                for item in values or []:
                    value = item.get("value", "")
                    if value and contains_cjk(value):
                        aliases.add(value)
        return aliases


def collect_fixture_teams(
    api: ApiFootballClient,
    days_before: int = 1,
    days_after: int = 14,
) -> dict[int, TeamAliasRecord]:
    fixtures = api.fixtures_by_date_window(
        datetime.now(timezone.utc),
        days_before=days_before,
        days_after=days_after,
    )
    records: dict[int, TeamAliasRecord] = {}
    for item in fixtures:
        for side in ("home", "away"):
            team = (item.get("teams", {}).get(side) or {})
            team_id = team.get("id")
            name = (team.get("name") or "").strip()
            if not team_id or not name:
                continue
            team_id = int(team_id)
            if team_id not in records:
                records[team_id] = TeamAliasRecord(
                    api_team_id=team_id,
                    api_team_name=name,
                    country=(item.get("league", {}) or {}).get("country", "") or "",
                    national=bool(team.get("national")),
                )
    return records


def build_alias_records(
    days_before: int = 1,
    days_after: int = 14,
    max_teams: int | None = None,
) -> list[TeamAliasRecord]:
    api = ApiFootballClient()
    records = collect_fixture_teams(api, days_before=days_before, days_after=days_after)
    wikidata = WikidataAliasClient()
    items = list(records.values())
    if max_teams:
        items = items[:max_teams]
    for index, record in enumerate(items, 1):
        record.aliases.update(wikidata.chinese_aliases_for_team(record.api_team_name))
        logger.info(
            "alias build %s/%s team=%s aliases=%s",
            index,
            len(items),
            record.api_team_name,
            len(record.aliases),
        )
    return items


def write_alias_file(records: list[TeamAliasRecord], output: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "description": "Generated from API-Football fixture teams and Wikidata Chinese labels/aliases.",
        "aliases": [record.asdict() for record in records if record.asdict()["aliases"]],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "output": str(output),
        "teams_seen": len(records),
        "teams_with_aliases": len(payload["aliases"]),
        "alias_count": sum(len(item["aliases"]) for item in payload["aliases"]),
    }


def default_output_path() -> Path:
    return Path("data") / "team_aliases.generated.json"


def refresh_alias_file(
    output: Path | None = None,
    days_before: int = 1,
    days_after: int = 14,
    max_teams: int | None = None,
) -> dict[str, Any]:
    records = build_alias_records(days_before=days_before, days_after=days_after, max_teams=max_teams)
    return write_alias_file(records, output or default_output_path())
