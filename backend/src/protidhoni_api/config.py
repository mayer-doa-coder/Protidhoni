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
    data_encryption_key: SecretStr | None = None
    gateway_private_key: SecretStr | None = None
    gateway_webhook_token: SecretStr | None = None
    gateway_ussd_webhook_token: SecretStr | None = None
    gateway_phone_pepper: SecretStr | None = None
    gateway_public_base_url: str | None = None

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

    def configured_gateway_webhook_token(self) -> str | None:
        """Return Twilio's SMS webhook secret, or None when disabled.

        Same fail-closed rule as ``configured_ai_internal_token``: a blank or
        short secret is a deployment error, not permission to accept unsigned
        provider callbacks. A Twilio auth token is 32 hex characters, so the
        32-character floor never rejects a genuine credential.
        """
        token = self.gateway_webhook_token.get_secret_value() if self.gateway_webhook_token else ""
        if len(token) < 32 or token != token.strip():
            return None
        return token

    def configured_gateway_ussd_webhook_token(self) -> str | None:
        """Return the simulator/USSD-adapter secret, or None when disabled.

        SMS and USSD deliberately use different credentials and signature
        schemes.  A future telco adapter can replace the simulator verifier
        without weakening or pretending to be Twilio authentication.
        """
        token = (
            self.gateway_ussd_webhook_token.get_secret_value()
            if self.gateway_ussd_webhook_token
            else ""
        )
        if len(token) < 32 or token != token.strip():
            return None
        return token

    def configured_gateway_phone_pepper(self) -> str | None:
        """Return the HMAC pepper used to pseudonymise caller phone numbers.

        Without a strong pepper the rate-limit key would be a bare phone-number
        hash, which is trivially reversible by brute force over a national
        numbering plan. Returning None here disables the gateway rather than
        letting it fall back to a weak identifier.
        """
        pepper = self.gateway_phone_pepper.get_secret_value() if self.gateway_phone_pepper else ""
        if len(pepper) < 32 or pepper != pepper.strip():
            return None
        return pepper

    @model_validator(mode="after")
    def _check_gateway_public_base_url(self) -> "Settings":
        # Compose passes "" for an unset optional variable, so blank must mean
        # "not configured" rather than crashing the process at startup.
        if self.gateway_public_base_url is not None and not self.gateway_public_base_url.strip():
            object.__setattr__(self, "gateway_public_base_url", None)
        if self.gateway_public_base_url is None:
            return self
        parsed = urlsplit(self.gateway_public_base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "PROTIDHONI_GATEWAY_PUBLIC_BASE_URL must be an HTTPS origin without "
                "credentials, paths, queries, or fragments"
            )
        return self

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
