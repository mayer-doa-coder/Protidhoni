import hashlib
import hmac
from typing import Annotated

from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from .classifier import build_classifier, classify_report
from .schemas import (
    ClassificationReport,
    ClassificationResult,
    InternalTranslationRequest,
    InternalTranslationResponse,
)
from .settings import Settings, get_settings
from .translation import TranslationUnavailable, translation_provider

internal_token_header = APIKeyHeader(
    name="X-Internal-Service-Token",
    scheme_name="InternalServiceToken",
    description="Internal backend-to-AI credential; never a browser credential.",
    auto_error=False,
)


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
    configured_model: str
    active_classifier: str


def _token_digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def _require_internal_token(configured: Settings, presented_token: str | None) -> None:
    expected_token = configured.configured_ai_internal_token()
    if expected_token is None:
        raise HTTPException(
            status_code=503, detail="AI internal service token is not configured."
        )
    if presented_token is None or not hmac.compare_digest(
        _token_digest(presented_token), _token_digest(expected_token)
    ):
        raise HTTPException(status_code=401, detail="Invalid internal service token.")


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    classifier = build_classifier(
        str(configured.fine_tuned_model_path)
        if configured.fine_tuned_model_path is not None
        else None
    )
    provider = translation_provider(
        configured.translation_base_url, configured.translation_api_key_value()
    )
    app = FastAPI(title="Protidhoni AI service", version=configured.app_version)

    @app.exception_handler(RequestValidationError)
    async def contract_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=400, content={"detail": jsonable_encoder(exc.errors())}
        )

    @app.get("/health", response_model=HealthResponse, tags=["operational"])
    async def health() -> HealthResponse:
        return HealthResponse(
            service="ai-service",
            status="ok",
            version=configured.app_version,
            configured_model=configured.model_id,
            active_classifier=classifier.model_name,
        )

    @app.post(
        "/ai/classify",
        response_model=ClassificationResult,
        tags=["classification"],
    )
    async def classify(
        report: ClassificationReport,
        internal_token: Annotated[str | None, Security(internal_token_header)] = None,
    ) -> ClassificationResult:
        _require_internal_token(configured, internal_token)
        return classify_report(report, classifier)

    @app.post(
        "/ai/translate",
        response_model=InternalTranslationResponse,
        tags=["translation"],
    )
    async def translate(
        translation_request: InternalTranslationRequest,
        internal_token: Annotated[str | None, Security(internal_token_header)] = None,
    ) -> InternalTranslationResponse:
        _require_internal_token(configured, internal_token)
        try:
            translated = await run_in_threadpool(
                provider.translate,
                translation_request.text,
                translation_request.source_language,
                translation_request.target_language,
            )
            return InternalTranslationResponse(
                text=translated.text,
                source_language=translated.source_language,
                target_language=translated.target_language,
                provider=translated.provider,
            )
        except (TranslationUnavailable, ValidationError, ValueError) as error:
            raise HTTPException(
                status_code=503, detail="Translation is temporarily unavailable."
            ) from error

    return app


app = create_app()
