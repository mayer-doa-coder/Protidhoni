import hmac
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .classifier import MODEL_NAME, classify_report
from .schemas import ClassificationReport, ClassificationResult
from .settings import Settings, get_settings


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
    configured_model: str
    active_classifier: str


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
    app = FastAPI(title="Protidhoni AI service", version=configured.app_version)

    @app.get("/health", response_model=HealthResponse, tags=["operational"])
    async def health() -> HealthResponse:
        return HealthResponse(
            service="ai-service",
            status="ok",
            version=configured.app_version,
            configured_model=configured.model_id,
            active_classifier=MODEL_NAME,
        )

    @app.post(
        "/ai/classify",
        response_model=ClassificationResult,
        tags=["classification"],
    )
    async def classify(
        report: ClassificationReport,
        internal_token: Annotated[
            str | None, Header(alias="X-Internal-Service-Token")
        ] = None,
    ) -> ClassificationResult:
        if configured.ai_internal_token is None:
            raise HTTPException(
                status_code=503, detail="AI internal service token is not configured."
            )
        if internal_token is None or not hmac.compare_digest(
            internal_token, configured.ai_internal_token
        ):
            raise HTTPException(
                status_code=401, detail="Invalid internal service token."
            )
        return classify_report(report)

    return app


app = create_app()
