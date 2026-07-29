from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from .config import get_settings
from .ratelimit import ClientIpRateLimitMiddleware
from .routes import router as reports_router


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool: AsyncConnectionPool | None = None
    if settings.database_url:
        pool = AsyncConnectionPool(conninfo=settings.database_url, open=False, min_size=1, max_size=10)
        await pool.open()
    app.state.db_pool = pool
    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


def create_app() -> FastAPI:
    """Create the API process. Phase 1 adds report persistence behind the
    frozen contract; database access is optional at startup so /health stays
    usable even when PROTIDHONI_DATABASE_URL is unset (e.g. this test suite)."""
    app = FastAPI(
        title="Protidhoni API",
        version=get_settings().app_version,
        docs_url="/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.add_middleware(ClientIpRateLimitMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _contract_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # contracts/openapi.yaml declares 400 for malformed request bodies;
        # FastAPI's default of 422 would silently diverge from the frozen contract.
        return JSONResponse(status_code=400, content={"detail": exc.errors()})

    @app.get("/health", response_model=HealthResponse, tags=["operational"])
    async def health() -> HealthResponse:
        return HealthResponse(service="backend", status="ok", version=get_settings().app_version)

    app.include_router(reports_router)

    return app


app = create_app()
