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

from .models import Report

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


class ReportPage(TypedDict):
    reports: list[dict]
    next_since: str | None


async def insert_report(pool: AsyncConnectionPool, report: Report) -> IngestOutcome:
    params = {
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
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_INSERT_SQL, params)
        row = await cur.fetchone()
        return "accepted" if row is not None else "duplicate"


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
    async with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(_SELECT_SQL, params)
        rows = await cur.fetchall()

    reports: list[dict] = []
    latest_received_at: datetime | None = None
    for row in rows:
        report_dict = dict(row["raw_message"])
        report_dict["priority"] = row["priority"]
        report_dict["verification"] = {
            "status": row["verification_status"],
            "corroboration_count": row["corroboration_count"],
        }
        # Retrievable from the server means, by definition, already synced;
        # the client-local sync_status the sender stored is not meaningful here.
        report_dict["sync_status"] = "synced"
        reports.append(report_dict)
        if latest_received_at is None or row["received_at"] > latest_received_at:
            latest_received_at = row["received_at"]

    return {
        "reports": reports,
        "next_since": latest_received_at.isoformat() if latest_received_at else None,
    }
