import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (ROOT, BACKEND):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("API_FOOTBALL_KEYS", "")
