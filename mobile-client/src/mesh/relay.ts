import type { CrisisReport } from "../contracts/report";
import { base64Decode, base64Encode } from "../crypto/base64";
import { getOrCreateDeviceIdentity } from "../crypto/identity";
import { utf8Decode, utf8Encode } from "../crypto/utf8";
import type { SqliteExecutor } from "../db/executor";
import { enqueueReport, listUnsyncedReports, updateSyncStatus } from "../db/queue";
import { NearbyConnections } from "../native/NearbyConnections";

/**
 * Store-and-forward relay (Protidhoni_Roadmap.md §5.1): whenever a peer
 * connects, this device offers every report in its local queue that isn't
 * already synced; whenever a payload arrives, it's enqueued (idempotent by
 * message_id, so re-received duplicates are dropped automatically) and
 * carries on unmodified until the next peer.
 *
 * Deliberately does NOT verify the Ed25519 signature before relaying —
 * per contracts/README.md and Protidhoni_Roadmap.md §5.5, a relay does not
 * need to be trusted; the backend verifies every report independently of
 * who carried it. Re-verifying here would only catch what the backend
 * already catches, at the cost of real Phase 1 scope.
 */

export function startMeshRelay(db: SqliteExecutor): () => void {
  // Returning the handler's promise (rather than `void`-ing it) costs
  // nothing in production — NativeEventEmitter ignores a listener's return
  // value — but lets tests await the real work deterministically instead of
  // guessing how many microtask ticks a fire-and-forget chain needs.
  const connectedSub = NearbyConnections.onConnected(({ endpointId }) => relayQueueTo(db, endpointId));
  const payloadSub = NearbyConnections.onPayloadReceived(({ dataBase64 }) =>
    handleIncomingPayload(db, dataBase64),
  );

  return () => {
    connectedSub.remove();
    payloadSub.remove();
  };
}

async function relayQueueTo(db: SqliteExecutor, endpointId: string): Promise<void> {
  const identity = await getOrCreateDeviceIdentity();
  const reports = await listUnsyncedReports(db);

  for (const report of reports) {
    if (report.ttl_hops <= 0) continue;

    const outgoing: CrisisReport = {
      ...report,
      ttl_hops: report.ttl_hops - 1,
      relay_path: [...report.relay_path, identity.pubkeyHashB64],
      sync_status: "relayed",
    };

    try {
      const bytes = utf8Encode(JSON.stringify(outgoing));
      await NearbyConnections.sendPayload(endpointId, base64Encode(bytes));
      await updateSyncStatus(db, report.message_id, "relayed");
    } catch {
      // Best-effort: this peer may have disconnected mid-transfer. The report
      // stays queued and will be offered again at the next connection.
    }
  }
}

async function handleIncomingPayload(db: SqliteExecutor, dataBase64: string): Promise<void> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(utf8Decode(base64Decode(dataBase64)));
  } catch {
    return; // malformed payload from an incompatible/misbehaving peer
  }

  if (!isPlausibleReport(parsed)) return;
  await enqueueReport(db, parsed);
}

function isPlausibleReport(value: unknown): value is CrisisReport {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<CrisisReport>;
  return (
    typeof candidate.message_id === "string" &&
    typeof candidate.sync_status === "string" &&
    typeof candidate.signature === "object" &&
    candidate.signature !== null &&
    typeof candidate.signature.value === "string" &&
    typeof candidate.ttl_hops === "number"
  );
}
