"""Team name normalization, aliases, and match text parsing."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover - fallback for minimal envs
    fuzz = None
    process = None


CHINESE_NATIONAL_TEAM_ALIASES = {
    "中国": "China",
    "中国队": "China",
    "国足": "China",
    "日本": "Japan",
    "日本队": "Japan",
    "韩国": "South Korea",
    "韩国队": "South Korea",
    "朝鲜": "North Korea",
    "澳大利亚": "Australia",
    "澳洲": "Australia",
    "伊朗": "Iran",
    "沙特": "Saudi Arabia",
    "沙特阿拉伯": "Saudi Arabia",
    "卡塔尔": "Qatar",
    "阿联酋": "United Arab Emirates",
    "伊拉克": "Iraq",
    "约旦": "Jordan",
    "乌兹别克斯坦": "Uzbekistan",
    "泰国": "Thailand",
    "越南": "Vietnam",
    "印尼": "Indonesia",
    "印度尼西亚": "Indonesia",
    "马来西亚": "Malaysia",
    "美国": "USA",
    "美国队": "USA",
    "加拿大": "Canada",
    "墨西哥": "Mexico",
    "哥斯达黎加": "Costa Rica",
    "牙买加": "Jamaica",
    "巴西": "Brazil",
    "阿根廷": "Argentina",
    "乌拉圭": "Uruguay",
    "智利": "Chile",
    "哥伦比亚": "Colombia",
    "秘鲁": "Peru",
    "厄瓜多尔": "Ecuador",
    "巴拉圭": "Paraguay",
    "玻利维亚": "Bolivia",
    "委内瑞拉": "Venezuela",
    "英格兰": "England",
    "英格兰队": "England",
    "苏格兰": "Scotland",
    "威尔士": "Wales",
    "北爱尔兰": "Northern Ireland",
    "爱尔兰": "Ireland",
    "法国": "France",
    "瑞典": "Sweden",
    "西班牙": "Spain",
    "德国": "Germany",
    "意大利": "Italy",
    "葡萄牙": "Portugal",
    "比利时": "Belgium",
    "荷兰": "Netherlands",
    "克罗地亚": "Croatia",
    "丹麦": "Denmark",
    "挪威": "Norway",
    "芬兰": "Finland",
    "波兰": "Poland",
    "罗马尼亚": "Romania",
    "土耳其": "Turkey",
    "土耳其队": "Turkey",
    "希腊": "Greece",
    "瑞士": "Switzerland",
    "奥地利": "Austria",
    "捷克": "Czech Republic",
    "乌克兰": "Ukraine",
    "塞尔维亚": "Serbia",
    "斯洛文尼亚": "Slovenia",
    "斯洛伐克": "Slovakia",
    "匈牙利": "Hungary",
    "保加利亚": "Bulgaria",
    "阿尔巴尼亚": "Albania",
    "波黑": "Bosnia & Herzegovina",
    "波斯尼亚": "Bosnia & Herzegovina",
    "波斯尼亚和黑塞哥维那": "Bosnia & Herzegovina",
    "冰岛": "Iceland",
    "摩洛哥": "Morocco",
    "塞内加尔": "Senegal",
    "突尼斯": "Tunisia",
    "加纳": "Ghana",
    "尼日利亚": "Nigeria",
    "喀麦隆": "Cameroon",
    "埃及": "Egypt",
    "阿尔及利亚": "Algeria",
    "科特迪瓦": "Ivory Coast",
    "象牙海岸": "Ivory Coast",
    "南非": "South Africa",
    "马里": "Mali",
    "刚果民主共和国": "Congo DR",
    "民主刚果": "Congo DR",
    "刚果金": "Congo DR",
    "刚果（金）": "Congo DR",
    "刚果(金)": "Congo DR",
}

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
    "congo dr": "Congo DR",
    "dr congo": "Congo DR",
    "democratic republic of congo": "Congo DR",
    "bosnia and herzegovina": "Bosnia & Herzegovina",
    **CHINESE_NATIONAL_TEAM_ALIASES,
}


TEAM_SUFFIXES = ("国家队", "男足", "女足", "足球队", "队")


@dataclass(frozen=True)
class MatchQuery:
    home: str
    away: str
    raw: str
    raw_home: str = ""
    raw_away: str = ""


NATIONAL_TEAM_NAMES = set(CHINESE_NATIONAL_TEAM_ALIASES.values())


def normalize_key(name: str) -> str:
    key = (name or "").strip().lower()
    key = key.replace("-", " ")
    key = re.sub(r"\s+", " ", key)
    return "".join(ch for ch in key if ch.isalnum() or "\u4e00" <= ch <= "\u9fff").strip()


def contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text or "")


TEAM_ALIASES = {normalize_key(alias): canonical for alias, canonical in RAW_TEAM_ALIASES.items()}
_FILE_ALIAS_CACHE: dict[str, Any] = {"signature": None, "aliases": {}, "team_ids": {}}


def _default_alias_paths() -> list[Path]:
    paths = [
        Path(__file__).with_name("team_aliases.seed.json"),
        Path.cwd() / "data" / "team_aliases.generated.json",
    ]
    app_data_dir = os.getenv("APP_DATA_DIR")
    if app_data_dir:
        paths.append(Path(app_data_dir) / "team_aliases.generated.json")
    env_files = os.getenv("TEAM_ALIAS_FILE") or os.getenv("TEAM_ALIAS_FILES")
    if env_files:
        paths.extend(Path(item.strip()) for item in env_files.split(os.pathsep) if item.strip())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _alias_file_signature(paths: list[Path]) -> tuple[tuple[str, float | None], ...]:
    signature = []
    for path in paths:
        try:
            signature.append((str(path), path.stat().st_mtime))
        except OSError:
            signature.append((str(path), None))
    return tuple(signature)


def _iter_alias_records(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    if isinstance(data.get("aliases"), list):
        return [item for item in data["aliases"] if isinstance(item, dict)]
    records = []
    for alias, target in data.items():
        if isinstance(target, str):
            records.append({"alias": alias, "api_team_name": target})
    return records


def _record_aliases(record: dict[str, Any]) -> list[str]:
    aliases: list[str] = []
    for key in ("alias", "zh", "name"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            aliases.append(value.strip())
    extra = record.get("aliases")
    if isinstance(extra, list):
        aliases.extend(str(item).strip() for item in extra if str(item).strip())
    return aliases


def _load_alias_files(paths: list[Path]) -> tuple[dict[str, str], dict[str, int]]:
    aliases: dict[str, str] = {}
    team_ids: dict[str, int] = {}
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in _iter_alias_records(data):
            api_team_name = str(
                record.get("api_team_name") or record.get("canonical") or record.get("team_name") or ""
            ).strip()
            if not api_team_name:
                continue
            api_team_id = record.get("api_team_id") or record.get("team_id")
            for alias in _record_aliases(record):
                key = normalize_key(alias)
                if key:
                    aliases[key] = api_team_name
                    if api_team_id:
                        team_ids[key] = int(api_team_id)
            canonical_key = normalize_key(api_team_name)
            if canonical_key and api_team_id:
                team_ids[canonical_key] = int(api_team_id)
    return aliases, team_ids


def load_file_aliases(force: bool = False) -> dict[str, str]:
    paths = _default_alias_paths()
    signature = _alias_file_signature(paths)
    if force or _FILE_ALIAS_CACHE["signature"] != signature:
        aliases, team_ids = _load_alias_files(paths)
        _FILE_ALIAS_CACHE.update({"signature": signature, "aliases": aliases, "team_ids": team_ids})
    return dict(_FILE_ALIAS_CACHE["aliases"])


def load_file_alias_team_ids(force: bool = False) -> dict[str, int]:
    load_file_aliases(force=force)
    return dict(_FILE_ALIAS_CACHE["team_ids"])


def clear_file_alias_cache() -> None:
    _FILE_ALIAS_CACHE.update({"signature": None, "aliases": {}, "team_ids": {}})


def normalize_team_name(name: str, extra_aliases: dict[str, str] | None = None) -> str:
    cleaned = (name or "").strip()
    aliases = dict(TEAM_ALIASES)
    aliases.update(load_file_aliases())
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
                if suffix == "女足" and alias in NATIONAL_TEAM_NAMES:
                    return f"{alias} W"
                return alias
            return stripped or cleaned

    return cleaned


def is_likely_national_team(name: str) -> bool:
    normalized = normalize_team_name(name)
    if normalized.endswith(" W") and normalized[:-2] in NATIONAL_TEAM_NAMES:
        return True
    return normalized in NATIONAL_TEAM_NAMES


def api_team_search_variants(team_name: str) -> list[str]:
    normalized = normalize_team_name(team_name)
    variants = [normalized]
    replacements = {
        "Bosnia & Herzegovina": ["Bosnia and Herzegovina", "Bosnia"],
        "USA": ["United States"],
        "South Korea": ["Korea Republic"],
        "North Korea": ["Korea DPR"],
        "Czech Republic": ["Czechia"],
        "Turkey": ["Türkiye"],
        "Ivory Coast": ["Cote d'Ivoire"],
        "Congo DR": ["DR Congo", "Democratic Republic of Congo"],
        "United Arab Emirates": ["UAE"],
    }
    variants.extend(replacements.get(normalized, []))
    if normalized.endswith(" W"):
        base = normalized[:-2]
        variants.extend(f"{variant} W" for variant in replacements.get(base, []))
    seen: set[str] = set()
    unique: list[str] = []
    for item in variants:
        key = item.lower()
        if not item or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


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
    return MatchQuery(
        home=normalize_team_name(home),
        away=normalize_team_name(away),
        raw=cleaned,
        raw_home=home,
        raw_away=away,
    )


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
