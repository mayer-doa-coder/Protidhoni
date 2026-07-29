"""Report persistence: idempotent ingestion and bbox/time-windowed reads.

Only the columns backend/db/init.sql defines are touched here. ``raw_message``
holds the complete client-signed report exactly as received, so GET /reports
can reconstruct the full contract shape without re-deriving it; ``priority``,
``verification_status``, and ``corroboration_count`` are read from their own
columns (not from raw_message) because those are server-owned fields that
Phase 2's PATCH /reports/{id} will update independently of the original
signed content.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, TypedDict

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from .models import Report, VerificationStatus, verification_transition_allowed

IngestOutcome = Literal["accepted", "duplicate"]

_INSERT_SQL = """
INSERT INTO reports (
    message_id, sender_pubkey_hash, created_at, report_type, language,
    payload, location, raw_message, priority, verification_status, corroboration_count
)
VALUES (
    %(message_id)s::uuid, %(sender_pubkey_hash)s, %(created_at)s::timestamptz,
    %(report_type)s, %(language)s, %(payload)s,
    CASE WHEN %(lat)s IS NULL OR %(lng)s IS NULL THEN NULL
         ELSE ST_SetSRID(ST_MakePoint(%(lng)s, %(lat)s), 4326)::geography
    END,
    %(raw_message)s, %(priority)s, %(verification_status)s, %(corroboration_count)s
)
ON CONFLICT (message_id) DO NOTHING
RETURNING message_id
"""

_SELECT_SQL = """
SELECT raw_message, priority, verification_status, corroboration_count, received_at
FROM reports
WHERE (%(since)s::timestamptz IS NULL OR received_at > %(since)s::timestamptz)
  AND (
    %(min_lng)s::double precision IS NULL
    OR (location IS NOT NULL AND location::geometry &&
        ST_MakeEnvelope(%(min_lng)s, %(min_lat)s, %(max_lng)s, %(max_lat)s, 4326))
  )
ORDER BY received_at ASC
LIMIT %(limit)s
"""

_SELECT_REPORT_FOR_UPDATE_SQL = """
SELECT raw_message, priority, verification_status, corroboration_count, received_at
FROM reports
WHERE message_id = %(message_id)s::uuid
FOR UPDATE
"""

_UPDATE_VERIFICATION_SQL = """
UPDATE reports
SET verification_status = %(status)s,
    verification_note = CASE
        WHEN %(note_was_provided)s THEN %(responder_note)s
        ELSE verification_note
    END,
    verification_updated_at = NOW()
WHERE message_id = %(message_id)s::uuid
RETURNING raw_message, priority, verification_status, corroboration_count, received_at
"""

_SELECT_RAW_REPORT_SQL = """
SELECT raw_message
FROM reports
WHERE message_id = %(message_id)s::uuid
"""

_SELECT_REPORT_SQL = """
SELECT raw_message, priority, verification_status, corroboration_count, received_at
FROM reports
WHERE message_id = %(message_id)s::uuid
"""

_QUEUE_OUTBOUND_INSTRUCTION_SQL = """
INSERT INTO outbound_instructions (message_id, delivery_status)
VALUES (%(message_id)s::uuid, 'queued')
ON CONFLICT (message_id) DO NOTHING
"""


class ReportPage(TypedDict):
    reports: list[dict]
    next_since: str | None


class VerificationTransitionError(ValueError):
    def __init__(self, current: VerificationStatus, requested: VerificationStatus) -> None:
        self.current = current
        self.requested = requested
        super().__init__(f"verification status cannot transition from {current} to {requested}")


class InstructionConflictError(ValueError):
    """A UUID already exists but does not identify the same signed instruction."""


def _report_from_row(row: dict) -> Report:
    report_dict = dict(row["raw_message"])
    report_dict["priority"] = row["priority"]
    report_dict["verification"] = {
        "status": row["verification_status"],
        "corroboration_count": row["corroboration_count"],
    }
    report_dict["sync_status"] = "synced"
    return Report.model_validate(report_dict)


def _insert_params(report: Report) -> dict:
    return {
        "message_id": report.message_id,
        "sender_pubkey_hash": report.sender_pubkey_hash,
        "created_at": report.created_at,
        "report_type": report.type,
        "language": report.language,
        "payload": Jsonb(report.payload.model_dump(mode="json")),
        "lat": report.location.lat,
        "lng": report.location.lng,
        "raw_message": Jsonb(report.model_dump(mode="json")),
        "priority": report.priority,
        "verification_status": report.verification.status,
        "corroboration_count": report.verification.corroboration_count,
    }


async def insert_report(pool: AsyncConnectionPool, report: Report) -> IngestOutcome:
    params = _insert_params(report)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(_INSERT_SQL, params)
            row = await cur.fetchone()
            return "accepted" if row is not None else "duplicate"


async def queue_instruction(pool: AsyncConnectionPool, report: Report) -> IngestOutcome:
    """Persist a signed instruction and ensure it has an outbound queue entry.

    A retry with the same UUID and exact content is idempotent. Reusing an
    existing UUID for different content is a conflict, not a duplicate.
    """
    params = _insert_params(report)
    expected_raw = report.model_dump(mode="json")
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_INSERT_SQL, params)
            inserted_row = await cur.fetchone()
            outcome: IngestOutcome = "accepted" if inserted_row is not None else "duplicate"

            if inserted_row is None:
                await cur.execute(_SELECT_RAW_REPORT_SQL, {"message_id": report.message_id})
                existing = await cur.fetchone()
                if existing is None or existing["raw_message"] != expected_raw:
                    raise InstructionConflictError(
                        "message_id is already used by different report content"
                    )

            await cur.execute(_QUEUE_OUTBOUND_INSTRUCTION_SQL, {"message_id": report.message_id})
            return outcome


async def list_reports(
    pool: AsyncConnectionPool,
    *,
    since: datetime | None,
    bbox: tuple[float, float, float, float] | None,
    limit: int,
) -> ReportPage:
    min_lng, min_lat, max_lng, max_lat = bbox if bbox is not None else (None, None, None, None)
    params = {
        "since": since,
        "min_lng": min_lng,
        "min_lat": min_lat,
        "max_lng": max_lng,
        "max_lat": max_lat,
        "limit": limit,
    }
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_SELECT_SQL, params)
            rows = await cur.fetchall()

    reports: list[dict] = []
    latest_received_at: datetime | None = None
    for row in rows:
        # Retrievable from the server means, by definition, already synced;
        # the client-local sync_status the sender stored is not meaningful here.
        reports.append(_report_from_row(row).model_dump(mode="json"))
        if latest_received_at is None or row["received_at"] > latest_received_at:
            latest_received_at = row["received_at"]

    return {
        "reports": reports,
        "next_since": latest_received_at.isoformat() if latest_received_at else None,
    }


async def get_report(pool: AsyncConnectionPool, *, message_id: str) -> Report | None:
    """Return one server-normalized report for responder-only operations."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_SELECT_REPORT_SQL, {"message_id": message_id})
            row = await cur.fetchone()
    return _report_from_row(row) if row is not None else None


async def update_report_verification(
    pool: AsyncConnectionPool,
    *,
    message_id: str,
    status: VerificationStatus,
    responder_note: str | None,
    note_was_provided: bool,
) -> Report | None:
    """Atomically validate and persist a responder verification transition."""
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_SELECT_REPORT_FOR_UPDATE_SQL, {"message_id": message_id})
            current_row = await cur.fetchone()
            if current_row is None:
                return None

            current_status: VerificationStatus = current_row["verification_status"]
            if not verification_transition_allowed(current_status, status):
                raise VerificationTransitionError(current_status, status)

            await cur.execute(
                _UPDATE_VERIFICATION_SQL,
                {
                    "message_id": message_id,
                    "status": status,
                    "responder_note": responder_note,
                    "note_was_provided": note_was_provided,
                },
            )
            updated_row = await cur.fetchone()
            if updated_row is None:  # Defensive: the row is locked and cannot disappear here.
                raise RuntimeError("verification update did not return the locked report")
            return _report_from_row(updated_row)
