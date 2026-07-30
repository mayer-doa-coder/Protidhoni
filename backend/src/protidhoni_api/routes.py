"""POST/GET /reports — Phase 1 report ingestion and retrieval.

Contract: contracts/openapi.yaml. One deliberate, documented extension over
the frozen Phase 0 contract: IngestResult.outcome gains a third value,
"rejected", for reports that are structurally valid JSON but fail identity/
signature verification or per-sender rate limiting. See contracts/README.md
for the reasoning — the alternative (failing the whole batch with 400 for one
bad report among many genuine ones) would defeat the batch endpoint's purpose
during exactly the bursty, multi-source conditions it exists for.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from . import db, translation
from .auth import require_responder_token
from .config import get_settings
from .crypto import SignatureVerificationError, verify_report_signature
from .ingestion import IngestOutcome, ingest_signed_report
from .models import (
    Report,
    ReportBatch,
    TranslationRequest,
    TranslationResponse,
    VerificationUpdate,
)
from .ratelimit import SenderRateLimiter

router = APIRouter(tags=["reports"])

_sender_limiter = SenderRateLimiter(max_reports_per_minute=10)

_BBOX_PATTERN = r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$"


def get_db_pool(request: Request) -> AsyncConnectionPool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not configured on this instance.")
    return pool


class IngestResult(BaseModel):
    message_id: str
    outcome: IngestOutcome


class IngestResponse(BaseModel):
    results: list[IngestResult]


class ReportCollection(BaseModel):
    reports: list[dict]
    next_since: str | None


class InstructionResponse(BaseModel):
    message_id: str
    delivery_status: Literal["queued"]


@router.post(
    "/translations",
    response_model=TranslationResponse,
    dependencies=[Depends(require_responder_token)],
)
async def translate_report(
    request: TranslationRequest,
    pool: AsyncConnectionPool = Depends(get_db_pool),
) -> TranslationResponse:
    """Translate one stored report without accepting client-controlled text."""
    report = await db.get_report(pool, message_id=str(request.message_id))
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")

    try:
        translated = await translation.request_ai_translation(
            base_url=get_settings().ai_service_url,
            internal_token=get_settings().configured_ai_internal_token(),
            text=report.payload.text,
            source_language=report.language,
            target_language=request.target_language,
        )
    except translation.TranslationUnavailable as error:
        raise HTTPException(
            status_code=503, detail="Translation is temporarily unavailable."
        ) from error
    except translation.TranslationProtocolError as error:
        raise HTTPException(
            status_code=502, detail="Translation service returned an invalid response."
        ) from error

    return TranslationResponse(
        message_id=request.message_id,
        source_language=translated.source_language,
        target_language=translated.target_language,
        text=translated.text,
        provider=translated.provider,
    )


@router.post("/reports", status_code=202, response_model=IngestResponse)
async def ingest_reports(
    batch: ReportBatch,
    pool: Annotated[AsyncConnectionPool, Depends(get_db_pool)],
) -> IngestResponse:
    results: list[IngestResult] = []
    for report in batch.reports:
        decision = await ingest_signed_report(pool, report, limiter=_sender_limiter)
        results.append(IngestResult(message_id=report.message_id, outcome=decision.outcome))
    return IngestResponse(results=results)


@router.get("/reports", response_model=ReportCollection)
async def get_reports(
    pool: Annotated[AsyncConnectionPool, Depends(get_db_pool)],
    since: Annotated[datetime | None, Query()] = None,
    bbox: Annotated[str | None, Query(pattern=_BBOX_PATTERN)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ReportCollection:
    bbox_tuple: tuple[float, float, float, float] | None = None
    if bbox is not None:
        min_lng, min_lat, max_lng, max_lat = (float(part) for part in bbox.split(","))
        if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180):
            raise HTTPException(status_code=400, detail="bbox longitude must be within -180..180")
        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            raise HTTPException(status_code=400, detail="bbox latitude must be within -90..90")
        if min_lng > max_lng or min_lat > max_lat:
            raise HTTPException(status_code=400, detail="bbox min must not exceed max")
        bbox_tuple = (min_lng, min_lat, max_lng, max_lat)

    page = await db.list_reports(pool, since=since, bbox=bbox_tuple, limit=limit)
    return ReportCollection(**page)


@router.patch(
    "/reports/{message_id}",
    response_model=Report,
    dependencies=[Depends(require_responder_token)],
)
async def update_report_verification(
    message_id: UUID,
    update: VerificationUpdate,
    pool: AsyncConnectionPool = Depends(get_db_pool),
) -> Report:
    try:
        report = await db.update_report_verification(
            pool,
            message_id=str(message_id),
            status=update.status,
            responder_note=update.responder_note,
            note_was_provided=update.note_was_provided,
        )
    except db.VerificationTransitionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    if report is None:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report


@router.post(
    "/instructions",
    status_code=202,
    response_model=InstructionResponse,
    dependencies=[Depends(require_responder_token)],
)
async def create_instruction(
    instruction: Report,
    pool: AsyncConnectionPool = Depends(get_db_pool),
) -> InstructionResponse:
    if instruction.type not in {"INSTRUCTION", "SAFE_ROUTE"}:
        raise HTTPException(
            status_code=400,
            detail="instructions must use type INSTRUCTION or SAFE_ROUTE",
        )

    try:
        verify_report_signature(instruction)
    except SignatureVerificationError as error:
        raise HTTPException(
            status_code=400,
            detail="instruction signature or signer identity is invalid",
        ) from error

    try:
        await db.queue_instruction(pool, instruction)
    except db.InstructionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    return InstructionResponse(message_id=instruction.message_id, delivery_status="queued")
