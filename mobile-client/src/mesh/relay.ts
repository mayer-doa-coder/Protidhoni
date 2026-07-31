import type { MapMark } from "../contracts/mark";
import type { CrisisReport } from "../contracts/report";
import { base64Decode, base64Encode } from "../crypto/base64";
import { getOrCreateDeviceIdentity } from "../crypto/identity";
import { verifyMark } from "../crypto/mark";
import { utf8Decode, utf8Encode } from "../crypto/utf8";
import { enqueueMark, listMarks } from "../db/marks";
import type { SqliteExecutor } from "../db/executor";
import { enqueueReport, listUnsyncedReports, updateSyncStatus } from "../db/queue";
import { NearbyConnections } from "../native/NearbyConnections";

/**
 * Store-and-forward relay (Protidhoni_Roadmap.md §5.1): whenever a peer
 * connects, this device offers every report in its local queue that isn't
 * already synced (plus every map mark it knows of — marks have no backend,
 * so "known" is the only state that exists); whenever a payload arrives,
 * it's enqueued (idempotent by message_id/mark_id, so re-received duplicates
 * are dropped automatically) and carries on unmodified until the next peer.
 *
 * Deliberately does NOT verify a report's Ed25519 signature before relaying —
 * per contracts/README.md and Protidhoni_Roadmap.md §5.5, a relay does not
 * need to be trusted; the backend verifies every report independently of
 * who carried it. Re-verifying here would only catch what the backend
 * already catches, at the cost of real Phase 1 scope.
 *
 * Marks are different: they have no backend to catch a forged one, so this
 * relay verifies every incoming mark's signature itself (crypto/mark.ts) —
 * the only check that will ever run for a mark.
 */

export type MeshRelayController = {
  /** Immediately offers one newly queued report to every connected peer. */
  relayReport(report: CrisisReport): Promise<number>;
  /** Immediately offers one newly placed map mark to every connected peer. */
  relayMark(mark: MapMark): Promise<number>;
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
    return Promise.all([
      relayQueueTo(db, endpointId),
      relayMarksTo(db, endpointId),
    ]).then(([sentReports, sentMarks]) => {
      if (sentReports > 0 || sentMarks > 0) onQueueChanged();
      return sentReports + sentMarks;
    });
  });
  const disconnectedSub = NearbyConnections.onDisconnected(({ endpointId }) => {
    connectedEndpoints.delete(endpointId);
  });
  const payloadSub = NearbyConnections.onPayloadReceived(
    async ({ endpointId, dataBase64 }) => {
      const parsed = decodePayload(dataBase64);
      if (parsed === null) return;

      if (isPlausibleReport(parsed)) {
        const incoming = await handleIncomingReport(db, parsed);
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
        return;
      }

      if (isPlausibleMark(parsed)) {
        const incoming = await handleIncomingMark(db, parsed);
        if (incoming) {
          onQueueChanged();
          const sent = await relayMarkToConnectedPeers(
            incoming,
            connectedEndpoints,
            endpointId,
          );
          if (sent > 0) onQueueChanged();
        }
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
    relayMark: async mark => {
      const sent = await relayMarkToConnectedPeers(mark, connectedEndpoints);
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

async function relayMarksTo(db: SqliteExecutor, endpointId: string): Promise<number> {
  const identity = await getOrCreateDeviceIdentity();
  const marks = await listMarks(db);
  let sent = 0;

  for (const mark of marks) {
    if (await sendMarkToPeer(mark, endpointId, identity.pubkeyHashB64)) {
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

async function relayMarkToConnectedPeers(
  mark: MapMark,
  connectedEndpoints: ReadonlySet<string>,
  excludedEndpointId?: string,
): Promise<number> {
  if (mark.ttl_hops <= 0) return 0;
  const endpoints = [...connectedEndpoints].filter(
    endpointId => endpointId !== excludedEndpointId,
  );
  if (endpoints.length === 0) return 0;

  const identity = await getOrCreateDeviceIdentity();
  const results = await Promise.all(
    endpoints.map(endpointId =>
      sendMarkToPeer(mark, endpointId, identity.pubkeyHashB64),
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

async function sendMarkToPeer(
  mark: MapMark,
  endpointId: string,
  identityHash: string,
): Promise<boolean> {
  if (mark.ttl_hops <= 0) return false;
  const outgoing: MapMark = {
    ...mark,
    ttl_hops: mark.ttl_hops - 1,
    relay_path: [...mark.relay_path, identityHash],
  };

  try {
    const bytes = utf8Encode(JSON.stringify(outgoing));
    await NearbyConnections.sendPayload(endpointId, base64Encode(bytes));
    return true;
  } catch {
    // Best-effort: this peer may have disconnected mid-transfer. The mark
    // stays queued and will be offered again at the next connection.
    return false;
  }
}

function decodePayload(dataBase64: string): unknown | null {
  try {
    return JSON.parse(utf8Decode(base64Decode(dataBase64)));
  } catch {
    return null; // malformed payload from an incompatible/misbehaving peer
  }
}

async function handleIncomingReport(
  db: SqliteExecutor,
  report: CrisisReport,
): Promise<CrisisReport | null> {
  return (await enqueueReport(db, report)) === "inserted" ? report : null;
}

async function handleIncomingMark(
  db: SqliteExecutor,
  mark: MapMark,
): Promise<MapMark | null> {
  if (!(await verifyMark(mark))) return null; // forged or corrupted — never store or forward
  return (await enqueueMark(db, mark)) === "inserted" ? mark : null;
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

function isPlausibleMark(value: unknown): value is MapMark {
  if (typeof value !== "object" || value === null) return false;
  const candidate = value as Partial<MapMark>;
  return (
    typeof candidate.mark_id === "string" &&
    typeof candidate.lat === "number" &&
    typeof candidate.lng === "number" &&
    typeof candidate.category === "string" &&
    typeof candidate.signature === "object" &&
    candidate.signature !== null &&
    typeof candidate.signature.value === "string" &&
    typeof candidate.ttl_hops === "number"
  );
}
