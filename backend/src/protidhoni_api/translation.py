"""Authenticated backend-to-AI translation client.

The public route sends only a stored report identifier to this backend. Raw
crisis text crosses the network only from the backend to the isolated AI
service, authenticated with the separate internal service credential.
"""

from __future__ import annotations

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

Language = Literal["bn", "en"]


class TranslationUnavailable(RuntimeError):
    """The configured AI service could not safely fulfil a request."""


class TranslationProtocolError(RuntimeError):
    """The AI service responded, but did not honour the internal contract."""


class InternalTranslationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    source_language: Language
    target_language: Language
    provider: str = Field(min_length=1, max_length=64)


async def _send_translation_request(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    internal_token: str,
    text: str,
    source_language: Language,
    target_language: Language,
) -> InternalTranslationResponse:
    try:
        response = await client.post(
            f"{base_url.rstrip('/')}/ai/translate",
            headers={"X-Internal-Service-Token": internal_token},
            json={
                "text": text,
                "source_language": source_language,
                "target_language": target_language,
            },
        )
    except httpx.TimeoutException as error:
        raise TranslationUnavailable("AI translation service timed out.") from error
    except httpx.RequestError as error:
        raise TranslationUnavailable("AI translation service is unavailable.") from error

    if response.status_code in {401, 403, 429, 503, 504} or response.status_code >= 500:
        raise TranslationUnavailable("AI translation service is unavailable.")
    if response.status_code != 200:
        raise TranslationProtocolError("AI translation service rejected a valid internal request.")
    try:
        translated = InternalTranslationResponse.model_validate(response.json())
    except (ValidationError, ValueError) as error:
        raise TranslationProtocolError(
            "AI translation service returned an invalid translation."
        ) from error
    if (
        translated.source_language != source_language
        or translated.target_language != target_language
    ):
        raise TranslationProtocolError("AI translation service returned mismatched languages.")
    return translated


async def request_ai_translation(
    *,
    base_url: str,
    internal_token: str | None,
    text: str,
    source_language: Language,
    target_language: Language,
    timeout_seconds: float = 8.0,
    client: httpx.AsyncClient | None = None,
) -> InternalTranslationResponse:
    """Call the internal AI service without ever forwarding provider errors."""
    if internal_token is None:
        raise TranslationUnavailable("AI internal service credentials are not configured.")
    if client is not None:
        return await _send_translation_request(
            client,
            base_url=base_url,
            internal_token=internal_token,
            text=text,
            source_language=source_language,
            target_language=target_language,
        )
    timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 3.0))
    async with httpx.AsyncClient(timeout=timeout) as owned_client:
        return await _send_translation_request(
            owned_client,
            base_url=base_url,
            internal_token=internal_token,
            text=text,
            source_language=source_language,
            target_language=target_language,
        )
