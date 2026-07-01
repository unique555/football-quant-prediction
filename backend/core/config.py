from typing import List
from urllib.parse import urlparse, urlunparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 基础
    PROJECT_NAME: str = "Football Quant Prediction"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # 数据库
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "football_quant"
    POSTGRES_USER: str = "football"
    POSTGRES_PASSWORD: str = "changeme"
    DATABASE_URL_RAW: str = Field(default="", validation_alias="DATABASE_URL")

    @property
    def DATABASE_URL(self) -> str:
        raw = self._normalized_database_url(async_driver=True)
        if raw:
            return raw
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        raw = self._normalized_database_url(async_driver=False)
        if raw:
            return raw
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    def _normalized_database_url(self, async_driver: bool) -> str:
        raw = self.DATABASE_URL_RAW
        if not raw:
            return ""
        parsed = urlparse(raw)
        if parsed.scheme in {"postgres", "postgresql", "postgresql+asyncpg"}:
            scheme = "postgresql+asyncpg" if async_driver else "postgresql"
            return urlunparse(parsed._replace(scheme=scheme))
        return raw

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # Celery
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # JWT
    SECRET_KEY: str = "change-to-random-string-at-least-32-chars"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # 外部 API
    API_FOOTBALL_KEY: str = ""
    API_FOOTBALL_KEYS: str = ""
    API_FOOTBALL_HOST: str = "v3.football.api-sports.io"
    ODDS_API_KEY: str = ""
    ODDS_API_BASE: str = "https://api.odds-api.io/v4/sports"

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    # Runtime paths
    APP_DATA_DIR: str = "/app/data"
    REPORTS_DIR: str = "/app/reports"

    # MLflow
    MLFLOW_TRACKING_URI: str = ""

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "prod", "production", "false", "0", "no"}:
                return False
            if normalized in {"debug", "dev", "development", "true", "1", "yes"}:
                return True
        return value

    @field_validator("DATABASE_URL_RAW", mode="before")
    @classmethod
    def read_database_url(cls, value):
        if value:
            return value
        import os

        return os.getenv("DATABASE_URL", "")

    @property
    def API_FOOTBALL_PRIMARY_KEY(self) -> str:
        if self.API_FOOTBALL_KEY:
            return self.API_FOOTBALL_KEY
        keys = [key.strip() for key in self.API_FOOTBALL_KEYS.split(",") if key.strip()]
        return keys[0] if keys else ""

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"


settings = Settings()
