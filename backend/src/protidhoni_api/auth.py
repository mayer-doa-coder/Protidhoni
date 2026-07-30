"""Authorization for responder-only API operations."""

from __future__ import annotations

import hashlib
import hmac
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import get_settings

responder_token_header = APIKeyHeader(
    name="X-Responder-Token",
    scheme_name="ResponderToken",
    description="Responder credential required for verification, instructions, and translations.",
    auto_error=False,
)


def _token_digest(value: str) -> bytes:
    """Hash tokens before constant-time comparison so both operands have equal length."""
    return hashlib.sha256(value.encode("utf-8")).digest()


def require_responder_token(
    presented_token: Annotated[str | None, Security(responder_token_header)],
) -> None:
    configured_secret = get_settings().responder_token
    configured_token = configured_secret.get_secret_value() if configured_secret else ""
    if len(configured_token) < 32 or configured_token != configured_token.strip():
        # A missing server credential is a deployment/configuration failure. It
        # must never turn a privileged endpoint into an anonymous endpoint.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Responder authorization is not securely configured on this instance.",
        )

    if presented_token is None or not hmac.compare_digest(
        _token_digest(presented_token), _token_digest(configured_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid responder credentials.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
