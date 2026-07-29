from fastapi import FastAPI
from pydantic import BaseModel

from .config import get_settings


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str


def create_app() -> FastAPI:
    """Create the Phase 0 API process without starting database-dependent features."""
    app = FastAPI(
        title="Protidhoni API",
        version=get_settings().app_version,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.get("/health", response_model=HealthResponse, tags=["operational"])
    async def health() -> HealthResponse:
        return HealthResponse(service="backend", status="ok", version=get_settings().app_version)

    return app


app = create_app()
