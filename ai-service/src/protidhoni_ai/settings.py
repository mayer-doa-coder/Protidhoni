from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROTIDHONI_", extra="ignore")

    model_id: str = "csebuetnlp/banglabert"
    app_version: str = "0.1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
