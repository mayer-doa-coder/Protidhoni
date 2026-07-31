from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PROTIDHONI_", extra="ignore")

    model_id: str = "csebuetnlp/banglabert"
    fine_tuned_model_path: Path | None = None
    app_version: str = "0.1.0"
    ai_internal_token: SecretStr | None = None
    translation_base_url: str | None = None
    translation_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _blank_fine_tuned_path_disables_it(self) -> "Settings":
        # An unset env var and an explicitly blank one (e.g. Docker Compose's
        # `${VAR:-}` default) must behave identically: rules classifier stays
        # active. Without this, Path("") resolves to the working directory,
        # which is a real directory and would fail confusingly at model load.
        if self.fine_tuned_model_path is not None and str(
            self.fine_tuned_model_path
        ).strip() in ("", "."):
            object.__setattr__(self, "fine_tuned_model_path", None)
        return self

    @model_validator(mode="after")
    def _validate_translation_origin(self) -> "Settings":
        if self.translation_base_url is None or not self.translation_base_url.strip():
            object.__setattr__(self, "translation_base_url", None)
            return self
        origin = self.translation_base_url.strip().rstrip("/")
        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PROTIDHONI_TRANSLATION_BASE_URL must be an HTTP(S) origin without "
                "credentials, paths, queries, or fragments"
            )
        object.__setattr__(self, "translation_base_url", origin)
        return self

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
