"""
全局配置 — 所有 Key 从环境变量或 .env 文件读取
用法: cp .env.example .env → 编辑 .env → 正常运行
"""

import os


# 自动加载 .env 文件
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                if key and value and key not in os.environ:
                    os.environ[key.strip()] = value.strip().strip('"').strip("'")


_load_dotenv()

# OddsPapi
ODDSPAPI_KEY = os.getenv("ODDSPAPI_KEY", "")

# football-data.org (逗号分隔多个 Key)
_raw = os.getenv("FOOTBALL_DATA_KEYS", "")
FOOTBALL_DATA_KEYS = [k.strip() for k in _raw.split(",") if k.strip()] if _raw else []

# API-Football (已暂停, 备用)
_raw2 = os.getenv("API_FOOTBALL_KEYS", "")
API_FOOTBALL_KEYS = [k.strip() for k in _raw2.split(",") if k.strip()] if _raw2 else []
