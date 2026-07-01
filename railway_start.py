#!/usr/bin/env python3
"""Railway startup for the Telegram-first worker."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT))


def run_migrations() -> None:
    if not os.getenv("DATABASE_URL"):
        print("Railway: DATABASE_URL not set, skipping Alembic migration", flush=True)
        return
    print("Railway: running Alembic migrations...", flush=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=str(BACKEND),
        check=True,
    )


def main() -> None:
    run_migrations()
    from bot_app.main import main as bot_main

    bot_main()


if __name__ == "__main__":
    main()
