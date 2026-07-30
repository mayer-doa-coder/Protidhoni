"""Shared signed-report ingestion policy.

Both ``POST /reports`` and the feature-phone gateway use this module.  Keeping
signature verification, rate limiting, duplicate handling, and persistence in
one place prevents an authenticated gateway route from accidentally becoming a
less-strict path into the reports table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from psycopg_pool import AsyncConnectionPool

from . import db
from .crypto import SignatureVerificationError, verify_report_signature
from .models import Report
from .ratelimit import SlidingWindowLimiter

IngestOutcome = Literal["accepted", "duplicate", "rejected"]
RejectionReason = Literal["invalid_signature", "rate_limited"]


@dataclass(frozen=True)
class IngestionDecision:
    outcome: IngestOutcome
    rejection_reason: RejectionReason | None = None


async def ingest_signed_report(
    pool: AsyncConnectionPool,
    report: Report,
    *,
    limiter: SlidingWindowLimiter,
    rate_limit_key: str | None = None,
    check_duplicate_first: bool = False,
) -> IngestionDecision:
    """Verify and ingest one report under the supplied rate-limit identity.

    Public report batches omit ``rate_limit_key`` and are limited by the
    cryptographically verified sender identity.  The gateway supplies a
    peppered phone pseudonym because all gateway reports share one signing key.
    Signature verification always happens before either identity is trusted.

    Provider retries use ``check_duplicate_first`` so a previously accepted
    callback remains idempotent even after its sender reaches the rate limit.
    """
    try:
        verified_sender_hash = verify_report_signature(report).sender_pubkey_hash
    except SignatureVerificationError:
        return IngestionDecision("rejected", "invalid_signature")

    if check_duplicate_first and await db.report_exists(pool, message_id=report.message_id):
        return IngestionDecision("duplicate")

    limiter_key = rate_limit_key or verified_sender_hash
    if not limiter.allow(limiter_key):
        return IngestionDecision("rejected", "rate_limited")

    return IngestionDecision(await db.insert_report(pool, report))
