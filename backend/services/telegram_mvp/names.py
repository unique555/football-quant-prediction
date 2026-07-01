"""Team name normalization, aliases, and match text parsing."""

from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - fallback for minimal envs
    fuzz = None
    process = None


RAW_TEAM_ALIASES = {
    "crb": "CRB",
    "crb al": "CRB",
    "clube de regatas brasil": "CRB",
    "雷加塔斯巴西": "CRB",
    "巴西雷加塔斯": "CRB",
    "botafogo sp": "Botafogo SP",
    "botafogo-sp": "Botafogo SP",
    "博塔弗戈sp": "Botafogo SP",
    "博塔弗戈圣保罗": "Botafogo SP",
    "保地花高sp": "Botafogo SP",
    "botafogo rj": "Botafogo RJ",
    "vps": "VPS",
    "瓦萨": "VPS",
    "图尔库国际": "Inter Turku",
    "法国": "France",
    "瑞典": "Sweden",
    "南非": "South Africa",
    "加拿大": "Canada",
    "美国": "USA",
    "巴西": "Brazil",
    "阿根廷": "Argentina",
    "日本": "Japan",
    "韩国": "South Korea",
    "中国": "China",
}


TEAM_SUFFIXES = ("国家队", "男足", "女足", "足球队", "队")


@dataclass(frozen=True)
class MatchQuery:
    home: str
    away: str
    raw: str


def normalize_key(name: str) -> str:
    key = (name or "").strip().lower()
    key = key.replace("-", " ")
    key = re.sub(r"\s+", " ", key)
    return "".join(ch for ch in key if ch.isalnum() or "\u4e00" <= ch <= "\u9fff").strip()


TEAM_ALIASES = {normalize_key(alias): canonical for alias, canonical in RAW_TEAM_ALIASES.items()}


def normalize_team_name(name: str, extra_aliases: dict[str, str] | None = None) -> str:
    cleaned = (name or "").strip()
    aliases = dict(TEAM_ALIASES)
    if extra_aliases:
        aliases.update({normalize_key(k): v for k, v in extra_aliases.items()})

    key = normalize_key(cleaned)
    if key in aliases:
        return aliases[key]

    for suffix in TEAM_SUFFIXES:
        if cleaned.endswith(suffix):
            stripped = cleaned[: -len(suffix)].strip()
            alias = aliases.get(normalize_key(stripped))
            if alias:
                return alias
            return stripped or cleaned

    return cleaned


def parse_match_text(text: str) -> MatchQuery | None:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^[/／]分析", "", cleaned).strip()
    if not cleaned:
        return None

    pattern = r"\s*(?:vs\.?|v\.?|对阵|对|－|-|—)\s*"
    parts = re.split(pattern, cleaned, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None

    home, away = parts[0].strip(), parts[1].strip()
    if not home or not away:
        return None
    return MatchQuery(home=normalize_team_name(home), away=normalize_team_name(away), raw=cleaned)


def team_similarity(query: str, candidate: str) -> float:
    q = normalize_key(normalize_team_name(query))
    c = normalize_key(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c or c in q:
        return 0.96
    if fuzz:
        return fuzz.WRatio(q, c) / 100
    return 0.0


def fuzzy_match_team(input_name: str, candidates: list[str], threshold: float = 0.8) -> str | None:
    if not candidates:
        return None
    if process and fuzz:
        result = process.extractOne(
            normalize_team_name(input_name),
            candidates,
            scorer=fuzz.WRatio,
        )
        if result and result[1] / 100 >= threshold:
            return str(result[0])
    best = max(candidates, key=lambda candidate: team_similarity(input_name, candidate))
    return best if team_similarity(input_name, best) >= threshold else None
