import NetInfo from "@react-native-community/netinfo";

import type { SqliteExecutor } from "../db/executor";
import {
  listUnsyncedReports,
  recordDeliveryResult,
  recordSyncFailure,
} from "../db/queue";

/** contracts/message-schema.json#/$defs/reportBatch: maxItems 100. */
const MAX_BATCH_SIZE = 100;

export type SyncConfig = {
  apiBaseUrl: string;
};

type IngestResult = { message_id: string; outcome: "accepted" | "duplicate" | "rejected" };
type IngestResponse = { results: IngestResult[] };

function isIngestResponse(value: unknown): value is IngestResponse {
  if (typeof value !== "object" || value === null) return false;
  const results = (value as { results?: unknown }).results;
  return Array.isArray(results) && results.every(result => {
    if (typeof result !== "object" || result === null) return false;
    const candidate = result as Partial<IngestResult>;
    return (
      typeof candidate.message_id === "string" &&
      candidate.message_id.length > 0 &&
      (candidate.outcome === "accepted" ||
        candidate.outcome === "duplicate" ||
        candidate.outcome === "rejected")
    );
  });
}

/**
 * Sync-when-online (Protidhoni_Roadmap.md §5.1): "any device that regains
 * connectivity automatically POSTs its whole local queue to the backend,
 * then keeps relaying over the mesh as normal." POST /reports is idempotent
 * by message_id (contracts/README.md), so re-sending an already-synced
 * report on a retry is harmless — the backend just reports "duplicate".
 *
 * Phase 2 stores a durable delivery result for every report. Rejected reports
 * remain unsynced and eligible for a later retry because the backend's frozen
 * response does not distinguish a permanent signature failure from temporary
 * rate limiting.
 */
export async function syncQueueToBackend(db: SqliteExecutor, config: SyncConfig): Promise<void> {
  const reports = await listUnsyncedReports(db);

  for (let start = 0; start < reports.length; start += MAX_BATCH_SIZE) {
    const batch = reports.slice(start, start + MAX_BATCH_SIZE);
    const batchIds = batch.map(report => report.message_id);

    let response: Response;
    try {
      response = await fetch(`${config.apiBaseUrl}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reports: batch }),
      });
    } catch {
      await recordSyncFailure(
        db,
        batchIds,
        "Backend unreachable. The report remains queued for the next connection.",
      );
      return;
    }

    if (!response.ok) {
      await recordSyncFailure(
        db,
        batchIds,
        `Backend returned HTTP ${response.status}. The report remains queued.`,
      );
      continue;
    }

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      await recordSyncFailure(db, batchIds, "Backend returned unreadable data. The report remains queued.");
      continue;
    }
    if (!isIngestResponse(body)) {
      await recordSyncFailure(db, batchIds, "Backend response was incomplete. The report remains queued.");
      continue;
    }

    const resultById = new Map(body.results.map(result => [result.message_id, result]));
    for (const messageId of batchIds) {
      const result = resultById.get(messageId);
      if (result) {
        await recordDeliveryResult(db, messageId, result.outcome);
      } else {
        await recordSyncFailure(
          db,
          [messageId],
          "Backend response omitted this report. It remains queued.",
        );
      }
    }
  }
}

export function startAutoSync(db: SqliteExecutor, config: SyncConfig): () => void {
  return NetInfo.addEventListener((state) => {
    if (state.isConnected && state.isInternetReachable !== false) {
      // eslint-disable-next-line no-void -- deliberately fire-and-forget; NetInfo's listener callback isn't awaited
      void syncQueueToBackend(db, config);
    }
  });
}
