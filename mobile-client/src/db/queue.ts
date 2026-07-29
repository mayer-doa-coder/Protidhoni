import type { CrisisReport, SyncStatus } from "../contracts/report";
import type { SqliteExecutor, SqliteRow } from "./executor";

/**
 * The local store-and-forward queue (Protidhoni_Roadmap.md §5.1/§5.3): every
 * report this device has authored or relayed lives here with a durable
 * sync_status, so the "my reports" view can show local/relayed/synced
 * without guessing, and the mesh layer can skip re-relaying messages it has
 * already seen (message_id is the primary key; enqueueReport is idempotent).
 *
 * `sync_status` is stored in its own column, not just inside the frozen
 * `report_json` blob, so it can be updated in place without needing to
 * re-parse/re-serialize the whole report; rowToReport() overlays the live
 * column value onto the reconstructed report on the way out.
 */

const CREATE_TABLE_SQL = `
CREATE TABLE IF NOT EXISTS report_queue (
  message_id TEXT PRIMARY KEY,
  report_json TEXT NOT NULL,
  sync_status TEXT NOT NULL,
  queued_at TEXT NOT NULL
)`;

export async function initReportQueueSchema(db: SqliteExecutor): Promise<void> {
  await db.execute(CREATE_TABLE_SQL);
}

export type EnqueueOutcome = "inserted" | "duplicate";

/** Idempotent by message_id — the same mesh dedup rule the backend applies
 * server-side (Protidhoni_Roadmap.md §5.1: "track message_ids you've
 * already relayed so the same SOS doesn't bounce around the mesh forever"). */
export async function enqueueReport(db: SqliteExecutor, report: CrisisReport): Promise<EnqueueOutcome> {
  const result = await db.execute(
    `INSERT OR IGNORE INTO report_queue (message_id, report_json, sync_status, queued_at) VALUES (?, ?, ?, ?)`,
    [report.message_id, JSON.stringify(report), report.sync_status, new Date().toISOString()],
  );
  return result.rowsAffected > 0 ? "inserted" : "duplicate";
}

function rowToReport(row: SqliteRow): CrisisReport {
  const report = JSON.parse(row.report_json as string) as CrisisReport;
  report.sync_status = row.sync_status as SyncStatus;
  return report;
}

export async function listAllReports(db: SqliteExecutor): Promise<CrisisReport[]> {
  const result = await db.execute(
    `SELECT report_json, sync_status FROM report_queue ORDER BY queued_at DESC`,
  );
  return result.rows.map(rowToReport);
}

export async function listUnsyncedReports(db: SqliteExecutor): Promise<CrisisReport[]> {
  const result = await db.execute(
    `SELECT report_json, sync_status FROM report_queue WHERE sync_status != 'synced' ORDER BY queued_at ASC`,
  );
  return result.rows.map(rowToReport);
}

export async function hasReport(db: SqliteExecutor, messageId: string): Promise<boolean> {
  const result = await db.execute(`SELECT 1 FROM report_queue WHERE message_id = ?`, [messageId]);
  return result.rows.length > 0;
}

const STATUS_RANK: Record<SyncStatus, number> = { local: 0, relayed: 1, synced: 2 };

/** local -> relayed -> synced is a one-way progression for this device's own
 * bookkeeping; never downgrade a report that already reached a later stage. */
export async function updateSyncStatus(
  db: SqliteExecutor,
  messageId: string,
  status: SyncStatus,
): Promise<void> {
  const result = await db.execute(`SELECT sync_status FROM report_queue WHERE message_id = ?`, [
    messageId,
  ]);
  const current = result.rows[0]?.sync_status as SyncStatus | undefined;
  if (current === undefined || STATUS_RANK[status] <= STATUS_RANK[current]) return;
  await db.execute(`UPDATE report_queue SET sync_status = ? WHERE message_id = ?`, [
    status,
    messageId,
  ]);
}
