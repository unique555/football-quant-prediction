"""
全局配置 — 所有 Key 从环境变量读取
用法: cp .env.example .env → 编辑 .env → 正常运行
"""
import os

# OddsPapi
ODDSPAPI_KEY = os.getenv("ODDSPAPI_KEY", "")

# football-data.org (逗号分隔多个 Key)
FOOTBALL_DATA_KEYS = os.getenv("FOOTBALL_DATA_KEYS", "").split(",") if os.getenv("FOOTBALL_DATA_KEYS") else []

# API-Football (已暂停, 备用)
API_FOOTBALL_KEYS = os.getenv("API_FOOTBALL_KEYS", "").split(",") if os.getenv("API_FOOTBALL_KEYS") else []
