from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from .config import get_settings
from .gateway_identity import gateway_pubkey_hash_or_none
from .gateway_routes import router as gateway_router
from .ratelimit import ClientIpRateLimitMiddleware
from .routes import router as reports_router


class HealthResponse(BaseModel):
    service: str
    status: str
    version: str
    # The SMS/USSD gateway's signing identity, or null when that path is not
    # configured. Published here so the dashboard can label feature-phone
    # reports without a build-time environment variable. Safe to expose: it is
    # a public-key hash that already appears in every gateway-originated report
    # returned by the public GET /reports.
    gateway_pubkey_hash: str | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    pool: AsyncConnectionPool | None = None
    if settings.database_url:
        pool = AsyncConnectionPool(
            conninfo=settings.database_url, open=False, min_size=1, max_size=10
        )
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
    settings = get_settings()
    app = FastAPI(
        title="Protidhoni API",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url=None,
        lifespan=_lifespan,
    )

    app.add_middleware(ClientIpRateLimitMiddleware)

    allowed_origins = settings.allowed_cors_origins()
    if allowed_origins:
        # Add CORS last so it remains the outermost middleware and includes
        # browser-readable CORS headers even on rate-limit/error responses.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
            allow_headers=["Content-Type", "X-Responder-Token"],
        )

    @app.exception_handler(RequestValidationError)
    async def _contract_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # contracts/openapi.yaml declares 400 for malformed request bodies;
        # FastAPI's default of 422 would silently diverge from the frozen contract.
        return JSONResponse(status_code=400, content={"detail": exc.errors()})

    @app.get("/health", response_model=HealthResponse, tags=["operational"])
    async def health() -> HealthResponse:
        return HealthResponse(
            service="backend",
            status="ok",
            version=get_settings().app_version,
            gateway_pubkey_hash=gateway_pubkey_hash_or_none(),
        )

    app.include_router(reports_router)
    app.include_router(gateway_router)

    return app


app = create_app()
