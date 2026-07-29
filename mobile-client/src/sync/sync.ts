import NetInfo from "@react-native-community/netinfo";

import type { SqliteExecutor } from "../db/executor";
import { listUnsyncedReports, updateSyncStatus } from "../db/queue";

/** contracts/message-schema.json#/$defs/reportBatch: maxItems 100. */
const MAX_BATCH_SIZE = 100;

export type SyncConfig = {
  apiBaseUrl: string;
};

type IngestResult = { message_id: string; outcome: "accepted" | "duplicate" | "rejected" };
type IngestResponse = { results: IngestResult[] };

function isIngestResponse(value: unknown): value is IngestResponse {
  return (
    typeof value === "object" &&
    value !== null &&
    Array.isArray((value as IngestResponse).results)
  );
}

/**
 * Sync-when-online (Protidhoni_Roadmap.md §5.1): "any device that regains
 * connectivity automatically POSTs its whole local queue to the backend,
 * then keeps relaying over the mesh as normal." POST /reports is idempotent
 * by message_id (contracts/README.md), so re-sending an already-synced
 * report on a retry is harmless — the backend just reports "duplicate".
 *
 * A "rejected" outcome (signature/rate-limit failure) is left queued as-is;
 * Phase 1 has no UI to surface *why* a report was rejected to the user yet.
 */
export async function syncQueueToBackend(db: SqliteExecutor, config: SyncConfig): Promise<void> {
  const reports = await listUnsyncedReports(db);

  for (let start = 0; start < reports.length; start += MAX_BATCH_SIZE) {
    const batch = reports.slice(start, start + MAX_BATCH_SIZE);

    let response: Response;
    try {
      response = await fetch(`${config.apiBaseUrl}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reports: batch }),
      });
    } catch {
      return; // offline again / host unreachable — retry on the next connectivity change
    }

    if (!response.ok) continue; // this batch was malformed; leave it queued rather than guess

    const body: unknown = await response.json().catch(() => null);
    if (!isIngestResponse(body)) continue;

    for (const result of body.results) {
      if (result.outcome === "accepted" || result.outcome === "duplicate") {
        await updateSyncStatus(db, result.message_id, "synced");
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
