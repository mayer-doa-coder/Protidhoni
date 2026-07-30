"""Generate missing local Phase 4 secrets without printing them.

This utility updates the repository's ignored ``.env`` file. Existing nonblank
values are preserved, every generated credential is independent, and no secret
is written to stdout. Real Twilio deployments must replace
``GATEWAY_WEBHOOK_TOKEN`` with the Account Auth Token from Twilio Console.
"""

from __future__ import annotations

import base64
import os
import secrets
import tempfile
from collections.abc import Callable
from pathlib import Path

SECRET_NAMES = (
    "GATEWAY_PRIVATE_KEY",
    "GATEWAY_WEBHOOK_TOKEN",
    "GATEWAY_USSD_WEBHOOK_TOKEN",
    "GATEWAY_PHONE_PEPPER",
)


def _secret(token_bytes: Callable[[int], bytes]) -> str:
    return base64.urlsafe_b64encode(token_bytes(32)).rstrip(b"=").decode("ascii")


def configure_env(
    env_path: Path,
    *,
    template_path: Path | None = None,
    token_bytes: Callable[[int], bytes] = secrets.token_bytes,
) -> list[str]:
    """Generate only missing/blank secrets and atomically update ``env_path``."""
    if env_path.exists():
        original = env_path.read_text(encoding="utf-8")
    elif template_path is not None and template_path.exists():
        original = template_path.read_text(encoding="utf-8")
    else:
        original = ""

    lines = original.splitlines()
    indexes: dict[str, int] = {}
    for index, line in enumerate(lines):
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key = line.split("=", 1)[0].strip()
        if key in SECRET_NAMES:
            indexes[key] = index

    generated: list[str] = []
    for name in SECRET_NAMES:
        index = indexes.get(name)
        if index is not None and lines[index].split("=", 1)[1].strip():
            continue
        value = _secret(token_bytes)
        if index is None:
            lines.append(f"{name}={value}")
        else:
            lines[index] = f"{name}={value}"
        generated.append(name)

    if "GATEWAY_PUBLIC_BASE_URL" not in indexes:
        lines.append("GATEWAY_PUBLIC_BASE_URL=")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{env_path.name}.", suffix=".tmp", dir=env_path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(lines).rstrip("\n") + "\n")
        os.replace(temporary_name, env_path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise
    return generated


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    generated = configure_env(
        repository_root / ".env",
        template_path=repository_root / ".env.example",
    )
    if generated:
        print("Generated local values for: " + ", ".join(generated))
    else:
        print("Gateway secrets were already configured; no values were changed.")
    print("Secret values were written only to the ignored .env file and were not displayed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
