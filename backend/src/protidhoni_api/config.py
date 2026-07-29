from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from environment variables, never source code."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROTIDHONI_", extra="ignore")

    database_url: str | None = None
    ai_internal_token: str | None = None
    app_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
