"""Generate a local Chinese team alias file.

Example:
    python scripts/build_team_aliases.py --days 14 --output data/team_aliases.generated.json
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from services.telegram_mvp.alias_builder import refresh_alias_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build API-Football Chinese team alias file.")
    parser.add_argument("--output", default="data/team_aliases.generated.json", help="Output JSON path.")
    parser.add_argument("--days-before", type=int, default=1, help="Past fixture days to include.")
    parser.add_argument("--days", "--days-after", dest="days_after", type=int, default=14, help="Future fixture days to include.")
    parser.add_argument("--max-teams", type=int, default=None, help="Limit teams for a small test run.")
    parser.add_argument("--verbose", action="store_true", help="Enable detailed logs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    summary = refresh_alias_file(
        output=Path(args.output),
        days_before=args.days_before,
        days_after=args.days_after,
        max_teams=args.max_teams,
    )
    print(
        "OK 中文队名词库已生成："
        f"{summary['output']} | 球队 {summary['teams_seen']} | "
        f"有中文别名 {summary['teams_with_aliases']} | 别名数 {summary['alias_count']}"
    )


if __name__ == "__main__":
    main()
