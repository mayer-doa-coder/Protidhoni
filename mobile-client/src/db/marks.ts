import type { MapMark } from "../contracts/mark";
import type { SqliteExecutor, SqliteRow } from "./executor";

/**
 * Local store for peer-visible map marks (db/queue.ts's report_queue, but for
 * pins instead of reports): every mark this device authored or relayed lives
 * here so the map can render everyone's pins offline and the mesh layer can
 * dedupe by mark_id instead of re-relaying the same pin forever.
 */

const CREATE_TABLE_SQL = `
CREATE TABLE IF NOT EXISTS map_marks (
  mark_id TEXT PRIMARY KEY,
  mark_json TEXT NOT NULL,
  queued_at TEXT NOT NULL
)`;

export async function initMapMarkSchema(db: SqliteExecutor): Promise<void> {
  await db.execute(CREATE_TABLE_SQL);
}

export type EnqueueMarkOutcome = "inserted" | "duplicate";

/** Idempotent by mark_id, the same dedup rule db/queue.ts uses for reports. */
export async function enqueueMark(db: SqliteExecutor, mark: MapMark): Promise<EnqueueMarkOutcome> {
  const result = await db.execute(
    `INSERT OR IGNORE INTO map_marks (mark_id, mark_json, queued_at) VALUES (?, ?, ?)`,
    [mark.mark_id, JSON.stringify(mark), new Date().toISOString()],
  );
  return result.rowsAffected > 0 ? "inserted" : "duplicate";
}

function rowToMark(row: SqliteRow): MapMark {
  return JSON.parse(row.mark_json as string) as MapMark;
}

export async function listMarks(db: SqliteExecutor): Promise<MapMark[]> {
  const result = await db.execute(`SELECT mark_json FROM map_marks ORDER BY queued_at DESC`);
  return result.rows.map(rowToMark);
}

export async function hasMark(db: SqliteExecutor, markId: string): Promise<boolean> {
  const result = await db.execute(`SELECT 1 FROM map_marks WHERE mark_id = ?`, [markId]);
  return result.rows.length > 0;
}
