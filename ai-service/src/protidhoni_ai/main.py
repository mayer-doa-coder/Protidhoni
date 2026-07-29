from fastapi import FastAPI
from pydantic import BaseModel

from .settings import get_settings


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
    configured_model: str


def create_app() -> FastAPI:
    app = FastAPI(title="Protidhoni AI service", version=get_settings().app_version)

    @app.get("/health", response_model=HealthResponse, tags=["operational"])
    async def health() -> HealthResponse:
        settings = get_settings()
        return HealthResponse(
            service="ai-service",
            status="ok",
            version=settings.app_version,
            configured_model=settings.model_id,
        )

    return app


app = create_app()
