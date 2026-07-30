from pathlib import Path

from scripts.configure_gateway_env import SECRET_NAMES, configure_env
from scripts.simulate_sms_gateway import _configured_token


def _values(path: Path) -> dict[str, str]:
    return {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in path.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.startswith("#")
    }


def test_generates_independent_secrets_without_replacing_existing_settings(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("POSTGRES_DB=keep-me\nGATEWAY_WEBHOOK_TOKEN=\n", encoding="utf-8")
    counter = 0

    def deterministic_bytes(length: int) -> bytes:
        nonlocal counter
        counter += 1
        return bytes([counter]) * length

    generated = configure_env(env_path, token_bytes=deterministic_bytes)
    values = _values(env_path)

    assert set(generated) == set(SECRET_NAMES)
    assert values["POSTGRES_DB"] == "keep-me"
    assert len({values[name] for name in SECRET_NAMES}) == len(SECRET_NAMES)
    assert all(len(values[name]) == 43 for name in SECRET_NAMES)
    assert values["GATEWAY_PUBLIC_BASE_URL"] == ""


def test_preserves_existing_nonblank_secrets(tmp_path) -> None:
    env_path = tmp_path / ".env"
    existing = "e" * 43
    env_path.write_text(f"GATEWAY_WEBHOOK_TOKEN={existing}\n", encoding="utf-8")

    generated = configure_env(env_path, token_bytes=lambda length: b"x" * length)
    values = _values(env_path)

    assert "GATEWAY_WEBHOOK_TOKEN" not in generated
    assert values["GATEWAY_WEBHOOK_TOKEN"] == existing


def test_simulator_process_token_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv("PROTIDHONI_GATEWAY_WEBHOOK_TOKEN", "process-secret")
    assert (
        _configured_token("PROTIDHONI_GATEWAY_WEBHOOK_TOKEN", "GATEWAY_WEBHOOK_TOKEN")
        == "process-secret"
    )
