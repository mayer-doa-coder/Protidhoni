from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from environment variables, never source code."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROTIDHONI_", extra="ignore")

    database_url: str | None = None
    ai_internal_token: str | None = None
    responder_token: SecretStr | None = None
    cors_origins: str = ""
    app_version: str = "0.1.0"

    def allowed_cors_origins(self) -> list[str]:
        origins = [origin.strip().rstrip("/") for origin in self.cors_origins.split(",")]
        origins = [origin for origin in origins if origin]
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "PROTIDHONI_CORS_ORIGINS must contain comma-separated HTTP(S) origins "
                    "without paths, credentials, queries, fragments, or wildcards"
                )
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
