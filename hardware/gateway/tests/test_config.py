from __future__ import annotations

import pytest

from protidhoni_lora_gateway.config import (
    DEFAULT_MESHTASTIC_PORT,
    GatewayConfigurationError,
    GatewaySettings,
)


def test_default_gateway_port_matches_pinned_meshtasticator_node_two() -> None:
    assert DEFAULT_MESHTASTIC_PORT == 4406
    assert GatewaySettings().meshtastic_port == 4406


def test_environment_configuration_is_explicit_and_bounded() -> None:
    settings = GatewaySettings.from_environment(
        {
            "PROTIDHONI_LORA_MESHTASTIC_HOST": "mesh-node",
            "PROTIDHONI_LORA_MESHTASTIC_PORT": "5500",
            "PROTIDHONI_LORA_BACKEND_URL": "https://api.example.test",
            "PROTIDHONI_LORA_BACKEND_ATTEMPTS": "4",
            "PROTIDHONI_LORA_FRAME_QUEUE_CAPACITY": "100",
        }
    )
    assert settings.meshtastic_host == "mesh-node"
    assert settings.meshtastic_port == 5500
    assert settings.backend_url == "https://api.example.test"
    assert settings.backend_attempts == 4
    assert settings.frame_queue_capacity == 100


@pytest.mark.parametrize(
    "values, message",
    [
        ({"PROTIDHONI_LORA_MESHTASTIC_PORT": "not-a-port"}, "must be an integer"),
        ({"PROTIDHONI_LORA_MESHTASTIC_PORT": "0"}, "between 1 and 65535"),
        ({"PROTIDHONI_LORA_MESHTASTIC_HOST": "bad host"}, "non-whitespace"),
        ({"PROTIDHONI_LORA_BACKEND_URL": "ftp://api.test"}, "HTTP"),
        ({"PROTIDHONI_LORA_BACKEND_URL": "https://user:pass@api.test"}, "credentials"),
        ({"PROTIDHONI_LORA_BACKEND_URL": "https://api.test/reports"}, "path"),
        ({"PROTIDHONI_LORA_BACKEND_URL": "https://api.test:99999"}, "invalid port"),
        ({"PROTIDHONI_LORA_BACKEND_URL": "https://api.test "}, "HTTP"),
        ({"PROTIDHONI_LORA_PENDING_CAPACITY": "33"}, "between 1 and 32"),
        (
            {
                "PROTIDHONI_LORA_PENDING_RETRY_SECONDS": "10",
                "PROTIDHONI_LORA_PENDING_TTL_SECONDS": "10",
            },
            "greater than",
        ),
        ({"PROTIDHONI_LORA_HTTP_TIMEOUT_SECONDS": "nan"}, "HTTP timeout"),
    ],
)
def test_configuration_fails_closed(values: dict[str, str], message: str) -> None:
    with pytest.raises(GatewayConfigurationError, match=message):
        GatewaySettings.from_environment(values)
