"""Opt-in Bangla/English translation adapter.

The frozen AI classification response has no translation field, so this module
is deliberately not exposed by a new HTTP route. It is ready for the backend
once the team agrees on a versioned contract extension. Until then it prevents
the dashboard from pretending that untranslated crisis text is English.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

Language = Literal["bn", "en"]


class TranslationUnavailable(RuntimeError):
    """No provider is configured or the configured provider could not respond."""


@dataclass(frozen=True)
class TranslationResult:
    text: str
    source_language: Language
    target_language: Language
    provider: str


class TranslationProvider(Protocol):
    def translate(
        self, text: str, source_language: Language, target_language: Language
    ) -> TranslationResult: ...


@dataclass(frozen=True)
class UnconfiguredTranslationProvider:
    def translate(
        self, text: str, source_language: Language, target_language: Language
    ) -> TranslationResult:
        del text, source_language, target_language
        raise TranslationUnavailable(
            "Translation is not configured. Original report text must be shown."
        )


@dataclass(frozen=True)
class LibreTranslateProvider:
    """Small client for a self-hosted or managed LibreTranslate instance."""

    base_url: str
    api_key: str | None = None
    timeout_seconds: float = 10.0

    def translate(
        self, text: str, source_language: Language, target_language: Language
    ) -> TranslationResult:
        if not text.strip():
            raise ValueError("Translation text must not be blank.")
        if source_language == target_language:
            return TranslationResult(
                text=text,
                source_language=source_language,
                target_language=target_language,
                provider="identity",
            )

        payload: dict[str, str] = {
            "q": text,
            "source": source_language,
            "target": target_language,
            "format": "text",
        }
        if self.api_key:
            payload["api_key"] = self.api_key
        url = f"{self.base_url.rstrip('/')}/translate"
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise TranslationUnavailable(
                f"Translation provider rejected the request ({error.code})."
            ) from error
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            raise TranslationUnavailable(
                "Translation provider is unavailable."
            ) from error

        translated = body.get("translatedText") if isinstance(body, dict) else None
        if not isinstance(translated, str) or not translated.strip():
            raise TranslationUnavailable(
                "Translation provider returned no translated text."
            )
        return TranslationResult(
            text=translated,
            source_language=source_language,
            target_language=target_language,
            provider="libretranslate",
        )


def translation_provider(
    base_url: str | None, api_key: str | None = None
) -> TranslationProvider:
    if base_url is None or not base_url.strip():
        return UnconfiguredTranslationProvider()
    return LibreTranslateProvider(base_url=base_url.strip(), api_key=api_key)
