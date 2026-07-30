"""Strict runtime configuration for the simulated LoRa gateway."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_MESHTASTIC_HOST = "127.0.0.1"
DEFAULT_MESHTASTIC_PORT = 4403
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 30
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
DEFAULT_BACKEND_ATTEMPTS = 3
DEFAULT_BACKEND_RETRY_DELAY_SECONDS = 0.5
DEFAULT_FRAME_QUEUE_CAPACITY = 512
DEFAULT_PENDING_CAPACITY = 32
DEFAULT_PENDING_RETRY_SECONDS = 10.0
DEFAULT_PENDING_TTL_SECONDS = 3_600.0


class GatewayConfigurationError(ValueError):
    """A gateway option or environment value is unsafe or invalid."""


def _environment_int(environment: Mapping[str, str], name: str, default: int) -> int:
    raw = environment.get(name)
    if raw is None:
        return default
    try:
        return int(raw, 10)
    except ValueError as error:
        raise GatewayConfigurationError(f"{name} must be an integer") from error


def _environment_float(environment: Mapping[str, str], name: str, default: float) -> float:
    raw = environment.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as error:
        raise GatewayConfigurationError(f"{name} must be a number") from error


@dataclass(frozen=True, slots=True)
class GatewaySettings:
    meshtastic_host: str = DEFAULT_MESHTASTIC_HOST
    meshtastic_port: int = DEFAULT_MESHTASTIC_PORT
    backend_url: str = DEFAULT_BACKEND_URL
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS
    http_timeout_seconds: float = DEFAULT_HTTP_TIMEOUT_SECONDS
    backend_attempts: int = DEFAULT_BACKEND_ATTEMPTS
    backend_retry_delay_seconds: float = DEFAULT_BACKEND_RETRY_DELAY_SECONDS
    frame_queue_capacity: int = DEFAULT_FRAME_QUEUE_CAPACITY
    pending_capacity: int = DEFAULT_PENDING_CAPACITY
    pending_retry_seconds: float = DEFAULT_PENDING_RETRY_SECONDS
    pending_ttl_seconds: float = DEFAULT_PENDING_TTL_SECONDS

    def __post_init__(self) -> None:
        if (
            not self.meshtastic_host
            or len(self.meshtastic_host) > 255
            or any(character.isspace() for character in self.meshtastic_host)
        ):
            raise GatewayConfigurationError(
                "Meshtastic host must be 1..255 non-whitespace characters"
            )
        if not 1 <= self.meshtastic_port <= 65_535:
            raise GatewayConfigurationError("Meshtastic port must be between 1 and 65535")

        parsed = urlsplit(self.backend_url)
        try:
            parsed_port = parsed.port
        except ValueError as error:
            raise GatewayConfigurationError("Backend URL contains an invalid port") from error
        if (
            self.backend_url != self.backend_url.strip()
            or any(character.isspace() for character in self.backend_url)
            or "\\" in self.backend_url
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise GatewayConfigurationError(
                "Backend URL must be an HTTP(S) origin without credentials, path, query, or fragment"
            )
        if parsed_port is not None and not 1 <= parsed_port <= 65_535:
            raise GatewayConfigurationError("Backend URL contains an invalid port")

        self._bounded_integer("connect timeout", self.connect_timeout_seconds, 1, 300)
        self._bounded_float("HTTP timeout", self.http_timeout_seconds, 0.1, 120.0)
        self._bounded_integer("backend attempts", self.backend_attempts, 1, 10)
        self._bounded_float("backend retry delay", self.backend_retry_delay_seconds, 0.0, 60.0)
        self._bounded_integer("frame queue capacity", self.frame_queue_capacity, 1, 4_096)
        self._bounded_integer("pending capacity", self.pending_capacity, 1, 32)
        self._bounded_float("pending retry interval", self.pending_retry_seconds, 0.1, 300.0)
        self._bounded_float("pending TTL", self.pending_ttl_seconds, 1.0, 86_400.0)
        if self.pending_ttl_seconds <= self.pending_retry_seconds:
            raise GatewayConfigurationError(
                "pending TTL must be greater than the pending retry interval"
            )

    @staticmethod
    def _bounded_integer(name: str, value: int, minimum: int, maximum: int) -> None:
        if isinstance(value, bool) or not minimum <= value <= maximum:
            raise GatewayConfigurationError(f"{name} must be between {minimum} and {maximum}")

    @staticmethod
    def _bounded_float(name: str, value: float, minimum: float, maximum: float) -> None:
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise GatewayConfigurationError(f"{name} must be between {minimum:g} and {maximum:g}")

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> GatewaySettings:
        values = os.environ if environment is None else environment
        return cls(
            meshtastic_host=values.get("PROTIDHONI_LORA_MESHTASTIC_HOST", DEFAULT_MESHTASTIC_HOST),
            meshtastic_port=_environment_int(
                values, "PROTIDHONI_LORA_MESHTASTIC_PORT", DEFAULT_MESHTASTIC_PORT
            ),
            backend_url=values.get("PROTIDHONI_LORA_BACKEND_URL", DEFAULT_BACKEND_URL),
            connect_timeout_seconds=_environment_int(
                values,
                "PROTIDHONI_LORA_CONNECT_TIMEOUT_SECONDS",
                DEFAULT_CONNECT_TIMEOUT_SECONDS,
            ),
            http_timeout_seconds=_environment_float(
                values, "PROTIDHONI_LORA_HTTP_TIMEOUT_SECONDS", DEFAULT_HTTP_TIMEOUT_SECONDS
            ),
            backend_attempts=_environment_int(
                values, "PROTIDHONI_LORA_BACKEND_ATTEMPTS", DEFAULT_BACKEND_ATTEMPTS
            ),
            backend_retry_delay_seconds=_environment_float(
                values,
                "PROTIDHONI_LORA_BACKEND_RETRY_DELAY_SECONDS",
                DEFAULT_BACKEND_RETRY_DELAY_SECONDS,
            ),
            frame_queue_capacity=_environment_int(
                values,
                "PROTIDHONI_LORA_FRAME_QUEUE_CAPACITY",
                DEFAULT_FRAME_QUEUE_CAPACITY,
            ),
            pending_capacity=_environment_int(
                values, "PROTIDHONI_LORA_PENDING_CAPACITY", DEFAULT_PENDING_CAPACITY
            ),
            pending_retry_seconds=_environment_float(
                values,
                "PROTIDHONI_LORA_PENDING_RETRY_SECONDS",
                DEFAULT_PENDING_RETRY_SECONDS,
            ),
            pending_ttl_seconds=_environment_float(
                values,
                "PROTIDHONI_LORA_PENDING_TTL_SECONDS",
                DEFAULT_PENDING_TTL_SECONDS,
            ),
        )
