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

export type MeshRelayController = {
  /** Immediately offers one newly queued report to every connected peer. */
  relayReport(report: CrisisReport): Promise<number>;
  stop(): void;
};

export function startMeshRelay(
  db: SqliteExecutor,
  onQueueChanged: () => void = () => undefined,
): MeshRelayController {
  const connectedEndpoints = new Set<string>();

  // Returning the handler's promise (rather than `void`-ing it) costs
  // nothing in production — NativeEventEmitter ignores a listener's return
  // value — but lets tests await the real work deterministically instead of
  // guessing how many microtask ticks a fire-and-forget chain needs.
  const connectedSub = NearbyConnections.onConnected(({ endpointId }) => {
    connectedEndpoints.add(endpointId);
    return relayQueueTo(db, endpointId).then(sent => {
      if (sent > 0) onQueueChanged();
      return sent;
    });
  });
  const disconnectedSub = NearbyConnections.onDisconnected(({ endpointId }) => {
    connectedEndpoints.delete(endpointId);
  });
  const payloadSub = NearbyConnections.onPayloadReceived(
    async ({ endpointId, dataBase64 }) => {
      const incoming = await handleIncomingPayload(db, dataBase64);
      if (incoming) {
        // Refresh an already-open My Reports screen as soon as the durable
        // local insert finishes; forwarding to the next peer may take time.
        onQueueChanged();
        const sent = await relayReportToConnectedPeers(
          db,
          incoming,
          connectedEndpoints,
          endpointId,
        );
        if (sent > 0) onQueueChanged();
      }
    },
  );

  return {
    relayReport: async report => {
      const sent = await relayReportToConnectedPeers(
        db,
        report,
        connectedEndpoints,
      );
      if (sent > 0) onQueueChanged();
      return sent;
    },
    stop: () => {
      connectedEndpoints.clear();
      connectedSub.remove();
      disconnectedSub.remove();
      payloadSub.remove();
    },
  };
}

async function relayQueueTo(db: SqliteExecutor, endpointId: string): Promise<number> {
  const identity = await getOrCreateDeviceIdentity();
  const reports = await listUnsyncedReports(db);
  let sent = 0;

  for (const report of reports) {
    if (await sendReportToPeer(db, report, endpointId, identity.pubkeyHashB64)) {
      sent += 1;
    }
  }
  return sent;
}

async function relayReportToConnectedPeers(
  db: SqliteExecutor,
  report: CrisisReport,
  connectedEndpoints: ReadonlySet<string>,
  excludedEndpointId?: string,
): Promise<number> {
  if (report.ttl_hops <= 0) return 0;
  const endpoints = [...connectedEndpoints].filter(
    endpointId => endpointId !== excludedEndpointId,
  );
  if (endpoints.length === 0) return 0;

  const identity = await getOrCreateDeviceIdentity();
  const results = await Promise.all(
    endpoints.map(endpointId =>
      sendReportToPeer(db, report, endpointId, identity.pubkeyHashB64),
    ),
  );
  return results.filter(Boolean).length;
}

async function sendReportToPeer(
  db: SqliteExecutor,
  report: CrisisReport,
  endpointId: string,
  identityHash: string,
): Promise<boolean> {
  if (report.ttl_hops <= 0) return false;
  const outgoing: CrisisReport = {
    ...report,
    ttl_hops: report.ttl_hops - 1,
    relay_path: [...report.relay_path, identityHash],
    sync_status: "relayed",
  };

  try {
    const bytes = utf8Encode(JSON.stringify(outgoing));
    await NearbyConnections.sendPayload(endpointId, base64Encode(bytes));
    await updateSyncStatus(db, report.message_id, "relayed");
    return true;
  } catch {
    // Best-effort: this peer may have disconnected mid-transfer. The report
    // stays queued and will be offered again at the next connection.
    return false;
  }
}

async function handleIncomingPayload(
  db: SqliteExecutor,
  dataBase64: string,
): Promise<CrisisReport | null> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(utf8Decode(base64Decode(dataBase64)));
  } catch {
    return null; // malformed payload from an incompatible/misbehaving peer
  }

  if (!isPlausibleReport(parsed)) return null;
  return (await enqueueReport(db, parsed)) === "inserted" ? parsed : null;
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
