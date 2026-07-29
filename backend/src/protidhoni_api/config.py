from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Values come from environment variables, never source code."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PROTIDHONI_", extra="ignore")

    database_url: str | None = None
    ai_internal_token: SecretStr | None = None
    ai_service_url: str = "http://ai-service:8001"
    responder_token: SecretStr | None = None
    cors_origins: str = ""
    app_version: str = "0.1.0"

    @model_validator(mode="after")
    def _check_ai_service_url(self) -> "Settings":
        parsed = urlsplit(self.ai_service_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PROTIDHONI_AI_SERVICE_URL must be an HTTP(S) origin without credentials, "
                "paths, queries, or fragments"
            )
        return self

    def configured_ai_internal_token(self) -> str | None:
        """Return a deployable internal credential, or None when disabled.

        Calling an AI service with a blank or short token would be a
        configuration error, not permission to make an anonymous request.
        """
        token = self.ai_internal_token.get_secret_value() if self.ai_internal_token else ""
        if len(token) < 32 or token != token.strip():
            return None
        return token

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
