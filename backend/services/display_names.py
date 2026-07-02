"""Display-name helpers for frontend-facing API responses."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from models.telegram_mvp import TeamAlias
from services.telegram_mvp.names import normalize_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def has_cjk(text: str | None) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text or "")


@lru_cache(maxsize=1)
def _seed_aliases() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "telegram_mvp" / "team_aliases.seed.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    aliases: dict[str, str] = {}
    for record in payload.get("aliases", []):
        api_name = str(record.get("api_team_name") or "").strip()
        if not api_name:
            continue
        for alias in record.get("aliases") or []:
            alias_text = str(alias or "").strip()
            if has_cjk(alias_text):
                aliases[normalize_key(api_name)] = alias_text
                break
    return aliases


async def team_display_name_map(
    session: AsyncSession,
    api_names: Iterable[str | None],
) -> dict[str, str]:
    names = sorted({str(name).strip() for name in api_names if str(name or "").strip()})
    if not names:
        return {}

    display = {name: _seed_aliases().get(normalize_key(name), name) for name in names}
    rows = (
        await session.execute(select(TeamAlias).where(TeamAlias.api_team_name.in_(names)))
    ).scalars().all()

    for row in rows:
        if has_cjk(row.alias):
            display[row.api_team_name] = row.alias

    return display


async def team_display_pair(
    session: AsyncSession,
    home_name: str | None,
    away_name: str | None,
) -> tuple[str | None, str | None]:
    display = await team_display_name_map(session, [home_name, away_name])
    return (
        display.get(home_name or "", home_name),
        display.get(away_name or "", away_name),
    )
