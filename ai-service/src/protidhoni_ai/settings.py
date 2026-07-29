from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROTIDHONI_", extra="ignore")

    model_id: str = "csebuetnlp/banglabert"
    fine_tuned_model_path: Path | None = None
    app_version: str = "0.1.0"
    ai_internal_token: str | None = None
    translation_base_url: str | None = None
    translation_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
