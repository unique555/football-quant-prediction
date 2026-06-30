import os
from typing import List

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

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def SYNC_DATABASE_URL(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

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
    API_FOOTBALL_HOST: str = "v3.api-football.com"
    ODDS_API_KEY: str = ""
    ODDS_API_BASE: str = "https://api.odds-api.io/v4/sports"

    # MLflow
    MLFLOW_TRACKING_URI: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
