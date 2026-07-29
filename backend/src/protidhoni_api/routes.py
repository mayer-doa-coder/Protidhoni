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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from . import db
from .crypto import SignatureVerificationError, verify_report_signature
from .models import Report, ReportBatch
from .ratelimit import SenderRateLimiter

router = APIRouter(tags=["reports"])

_sender_limiter = SenderRateLimiter(max_reports_per_minute=10)

_BBOX_PATTERN = r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$"


def get_db_pool(request: Request) -> AsyncConnectionPool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database is not configured on this instance.")
    return pool


IngestOutcome = Literal["accepted", "duplicate", "rejected"]


class IngestResult(BaseModel):
    message_id: str
    outcome: IngestOutcome


class IngestResponse(BaseModel):
    results: list[IngestResult]


class ReportCollection(BaseModel):
    reports: list[dict]
    next_since: str | None


def _verified_sender_hash_or_none(report: Report) -> str | None:
    """Return the cryptographically verified sender identity, if valid.

    Rate limiting must use this returned value, not an untrusted hash supplied
    by the request. In particular, an invalid signature must never consume a
    legitimate sender's quota.
    """
    try:
        return verify_report_signature(report).sender_pubkey_hash
    except SignatureVerificationError:
        return None


@router.post("/reports", status_code=202, response_model=IngestResponse)
async def ingest_reports(
    batch: ReportBatch,
    pool: Annotated[AsyncConnectionPool, Depends(get_db_pool)],
) -> IngestResponse:
    results: list[IngestResult] = []
    for report in batch.reports:
        verified_sender_hash = _verified_sender_hash_or_none(report)
        if verified_sender_hash is None:
            results.append(IngestResult(message_id=report.message_id, outcome="rejected"))
            continue
        if not _sender_limiter.allow(verified_sender_hash):
            results.append(IngestResult(message_id=report.message_id, outcome="rejected"))
            continue
        outcome = await db.insert_report(pool, report)
        results.append(IngestResult(message_id=report.message_id, outcome=outcome))
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
