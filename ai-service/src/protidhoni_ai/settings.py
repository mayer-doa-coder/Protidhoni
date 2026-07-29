from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROTIDHONI_", extra="ignore")

    model_id: str = "csebuetnlp/banglabert"
    fine_tuned_model_path: Path | None = None
    app_version: str = "0.1.0"
    ai_internal_token: SecretStr | None = None
    translation_base_url: str | None = None
    translation_api_key: SecretStr | None = None

    def configured_ai_internal_token(self) -> str | None:
        """Return a secure internal credential or keep internal routes disabled."""
        token = (
            self.ai_internal_token.get_secret_value() if self.ai_internal_token else ""
        )
        if len(token) < 32 or token != token.strip():
            return None
        return token

    def translation_api_key_value(self) -> str | None:
        return (
            self.translation_api_key.get_secret_value()
            if self.translation_api_key
            else None
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
