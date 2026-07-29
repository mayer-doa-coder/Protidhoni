import json
from io import BytesIO
from unittest.mock import patch

import pytest

from protidhoni_ai.translation import (
    LibreTranslateProvider,
    TranslationUnavailable,
    translation_provider,
)


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self._body = BytesIO(json.dumps(body).encode("utf-8"))

    def read(self) -> bytes:
        return self._body.read()

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args) -> None:
        return None


def test_unconfigured_translation_never_claims_to_translate() -> None:
    with pytest.raises(TranslationUnavailable, match="not configured"):
        translation_provider(None).translate("জরুরি সাহায্য", "bn", "en")


def test_libretranslate_adapter_sends_plain_text_request_and_validates_response() -> (
    None
):
    provider = LibreTranslateProvider("http://translator.test", api_key="secret")
    with patch(
        "protidhoni_ai.translation.urlopen",
        return_value=FakeResponse({"translatedText": "Emergency help"}),
    ) as request:
        result = provider.translate("জরুরি সাহায্য", "bn", "en")

    sent_request = request.call_args.args[0]
    assert sent_request.full_url == "http://translator.test/translate"
    assert json.loads(sent_request.data) == {
        "q": "জরুরি সাহায্য",
        "source": "bn",
        "target": "en",
        "format": "text",
        "api_key": "secret",
    }
    assert result.text == "Emergency help"
    assert result.provider == "libretranslate"


def test_translation_identity_does_not_send_report_text_to_a_provider() -> None:
    provider = LibreTranslateProvider("http://translator.test")
    with patch("protidhoni_ai.translation.urlopen") as request:
        result = provider.translate("Already English", "en", "en")

    request.assert_not_called()
    assert result.provider == "identity"
