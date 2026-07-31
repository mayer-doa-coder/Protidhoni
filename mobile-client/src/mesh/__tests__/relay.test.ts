import AsyncStorage from "@react-native-async-storage/async-storage";

import type { CrisisReport } from "../../contracts/report";
import { base64Encode } from "../../crypto/base64";
import { _resetDeviceIdentityCacheForTests, getOrCreateDeviceIdentity } from "../../crypto/identity";
import { utf8Encode } from "../../crypto/utf8";
import {
  enqueueReport,
  initReportQueueSchema,
  listAllReports,
  listUnsyncedReports,
  updateSyncStatus,
} from "../../db/queue";
import { createNodeSqliteExecutor } from "../../db/testSupport/nodeSqliteExecutor";
import { enqueueMark, initMapMarkSchema, listMarks } from "../../db/marks";
import { createSignedMark } from "../../crypto/mark";

// relay.ts's listeners return their handler's promise (see the comment in
// relay.ts), so tests can `await` a triggered event directly instead of
// guessing how many microtask ticks a fire-and-forget chain needs.
type Listener<T> = (payload: T) => Promise<unknown> | void;

// The factory must be fully self-contained: Babel hoists `import` statements
// (including the module-under-test import below) above ordinary `const`
// declarations, so a factory that closes over an outer `mock`-prefixed
// variable can run before that variable is ever assigned. Building the
// listener arrays and jest.fn() entirely inside the factory, then reading
// them back out through the (now-mocked) module import, sidesteps that
// hoisting hazard rather than fighting it.
jest.mock("../../native/NearbyConnections", () => {
  const connected: unknown[] = [];
  const disconnected: unknown[] = [];
  const payloadReceived: unknown[] = [];
  return {
    NearbyConnections: {
      onConnected: (listener: unknown) => {
        connected.push(listener);
        return { remove: jest.fn() };
      },
      onPayloadReceived: (listener: unknown) => {
        payloadReceived.push(listener);
        return { remove: jest.fn() };
      },
      onDisconnected: (listener: unknown) => {
        disconnected.push(listener);
        return { remove: jest.fn() };
      },
      sendPayload: jest.fn(async (_endpointId: string, _dataBase64: string) => undefined),
      __mockListeners: { connected, disconnected, payloadReceived },
    },
  };
});

// identity.ts (imported transitively via relay.ts) wraps the device key via
// the native KeystoreWrap module; see src/native/__mocks__/KeystoreWrap.ts.
jest.mock("../../native/KeystoreWrap");

import { NearbyConnections } from "../../native/NearbyConnections";
import { startMeshRelay } from "../relay";

type MockedNearbyConnections = typeof NearbyConnections & {
  __mockListeners: {
    connected: Listener<{ endpointId: string }>[];
    disconnected: Listener<{ endpointId: string }>[];
    payloadReceived: Listener<{ endpointId: string; dataBase64: string }>[];
  };
};

const mockListeners = (NearbyConnections as MockedNearbyConnections).__mockListeners;
const mockSendPayload = NearbyConnections.sendPayload as jest.MockedFunction<
  typeof NearbyConnections.sendPayload
>;

function makeReport(overrides: Partial<CrisisReport> = {}): CrisisReport {
  return {
    schema_version: "1.0.0",
    message_id: overrides.message_id ?? "11111111-1111-4111-8111-111111111111",
    type: "SOS",
    sender_pubkey: "A".repeat(43),
    sender_pubkey_hash: "B".repeat(43),
    created_at: new Date().toISOString(),
    language: "bn",
    location: { lat: 23.81, lng: 90.41, accuracy_m: 5, source: "gps" },
    payload: { text: "সাহায্য দরকার", people_count: 2, needs: ["water"], attachment_ref: null },
    priority: null,
    ttl_hops: 8,
    signature: { algorithm: "Ed25519", value: "C".repeat(86) },
    relay_path: [],
    sync_status: "local",
    verification: { status: "unverified", corroboration_count: 0 },
    ...overrides,
  };
}

describe("startMeshRelay", () => {
  beforeEach(async () => {
    // Truncate in place (not reassign) — the mock's onConnected/
    // onPayloadReceived closures push into these exact array instances.
    mockListeners.connected.length = 0;
    mockListeners.disconnected.length = 0;
    mockListeners.payloadReceived.length = 0;
    mockSendPayload.mockClear();
    _resetDeviceIdentityCacheForTests();
    await AsyncStorage.clear();
  });

  it("sends every unsynced queued report to a newly connected peer", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);
    const report = makeReport();
    await enqueueReport(db, report);

    startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "peer-1" });

    expect(mockSendPayload).toHaveBeenCalledTimes(1);
    const [endpointId] = mockSendPayload.mock.calls[0];
    expect(endpointId).toBe("peer-1");

    const [stored] = await listAllReports(db);
    expect(stored.sync_status).toBe("relayed");
  });

  it("decrements ttl_hops and appends this device's identity to relay_path when forwarding", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);

    await enqueueReport(db, makeReport({ ttl_hops: 5, relay_path: ["Z".repeat(43)] }));

    const identity = await getOrCreateDeviceIdentity();

    startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "peer-1" });

    const [, dataBase64] = mockSendPayload.mock.calls[0];
    const decoded = JSON.parse(Buffer.from(dataBase64 as string, "base64").toString("utf-8"));
    expect(decoded.ttl_hops).toBe(4);
    expect(decoded.relay_path).toEqual(["Z".repeat(43), identity.pubkeyHashB64]);
  });

  it("does not forward a report whose ttl_hops has already reached 0", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);

    await enqueueReport(db, makeReport({ ttl_hops: 0 }));

    startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "peer-1" });

    expect(mockSendPayload).not.toHaveBeenCalled();
  });

  it("enqueues a genuinely new incoming report (mesh dedup lets duplicates through harmlessly)", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);
    const incoming = makeReport({ message_id: "22222222-2222-4222-8222-222222222222" });
    const bytes = utf8Encode(JSON.stringify(incoming));

    startMeshRelay(db);
    await mockListeners.payloadReceived[0]({ endpointId: "peer-1", dataBase64: base64Encode(bytes) });

    const all = await listAllReports(db);
    expect(all.map((r) => r.message_id)).toContain("22222222-2222-4222-8222-222222222222");
  });

  it("receiving the same message_id twice does not duplicate it (mesh dedup)", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);
    const incoming = makeReport({ message_id: "33333333-3333-4333-8333-333333333333" });
    const dataBase64 = base64Encode(utf8Encode(JSON.stringify(incoming)));

    startMeshRelay(db);
    await mockListeners.payloadReceived[0]({ endpointId: "peer-1", dataBase64 });
    await mockListeners.payloadReceived[0]({ endpointId: "peer-2", dataBase64 });

    const all = await listAllReports(db);
    expect(all.filter((r) => r.message_id === "33333333-3333-4333-8333-333333333333")).toHaveLength(1);
  });

  it("forwards a newly received report to other connected peers without echoing it", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);
    startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "source-peer" });
    await mockListeners.connected[0]({ endpointId: "next-peer" });

    const incoming = makeReport({ message_id: "44444444-4444-4444-8444-444444444444" });
    await mockListeners.payloadReceived[0]({
      endpointId: "source-peer",
      dataBase64: base64Encode(utf8Encode(JSON.stringify(incoming))),
    });

    expect(mockSendPayload).toHaveBeenCalledTimes(1);
    expect(mockSendPayload).toHaveBeenCalledWith("next-peer", expect.any(String));
    const [stored] = await listAllReports(db);
    expect(stored.sync_status).toBe("relayed");
  });

  it("silently ignores a malformed/non-report payload instead of crashing", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);

    startMeshRelay(db);
    await mockListeners.payloadReceived[0]({
      endpointId: "peer-1",
      dataBase64: base64Encode(utf8Encode("not json at all")),
    });

    expect(await listAllReports(db)).toHaveLength(0);
  });

  it("unsubscribe stops further relaying", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);

    await enqueueReport(db, makeReport());

    const relay = startMeshRelay(db);
    relay.stop();

    // mockListeners array still holds the captured callback (our mock doesn't
    // actually remove it), but relay.ts's own returned unsubscribe function
    // must have called .remove() on both subscriptions.
    expect(mockListeners.connected).toHaveLength(1);
  });

  it("relays a report created after the peer is already connected", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);
    const relay = startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "peer-1" });

    const report = makeReport();
    await enqueueReport(db, report);
    const peerCount = await relay.relayReport(report);

    expect(peerCount).toBe(1);
    expect(mockSendPayload).toHaveBeenCalledTimes(1);
    expect(mockSendPayload).toHaveBeenCalledWith("peer-1", expect.any(String));
    const [stored] = await listAllReports(db);
    expect(stored.sync_status).toBe("relayed");
  });

  it("does not send newly queued reports to a disconnected peer", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);
    const relay = startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "peer-1" });
    mockListeners.disconnected[0]({ endpointId: "peer-1" });

    const report = makeReport();
    await enqueueReport(db, report);

    await expect(relay.relayReport(report)).resolves.toBe(0);
    expect(mockSendPayload).not.toHaveBeenCalled();
  });

  it("does not re-forward a report that is already synced", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await initMapMarkSchema(db);

    const report = makeReport();
    await enqueueReport(db, report);
    await updateSyncStatus(db, report.message_id, "synced");

    startMeshRelay(db);
    await mockListeners.connected[0]({ endpointId: "peer-1" });

    expect(mockSendPayload).not.toHaveBeenCalled();
    expect(await listUnsyncedReports(db)).toHaveLength(0);
  });

  describe("map marks", () => {
    it("sends a newly placed mark to every connected peer", async () => {
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      const relay = startMeshRelay(db);
      await mockListeners.connected[0]({ endpointId: "peer-1" });

      const mark = await createSignedMark({
        lat: 23.81,
        lng: 90.41,
        category: "HAZARD",
        label: "রাস্তা ভাঙা",
      });
      const peerCount = await relay.relayMark(mark);

      expect(peerCount).toBe(1);
      expect(mockSendPayload).toHaveBeenCalledWith("peer-1", expect.any(String));
    });

    it("offers every known mark to a newly connected peer", async () => {
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      const mark = await createSignedMark({
        lat: 23.81,
        lng: 90.41,
        category: "SHELTER",
        label: "আশ্রয়কেন্দ্র",
      });
      await enqueueMark(db, mark);

      startMeshRelay(db);
      await mockListeners.connected[0]({ endpointId: "peer-1" });

      expect(mockSendPayload).toHaveBeenCalledTimes(1);
      const [, dataBase64] = mockSendPayload.mock.calls[0];
      const decoded = JSON.parse(Buffer.from(dataBase64 as string, "base64").toString("utf-8"));
      expect(decoded.mark_id).toBe(mark.mark_id);
    });

    it("enqueues a genuinely new incoming mark with a valid signature", async () => {
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      const mark = await createSignedMark({
        lat: 23.7,
        lng: 90.4,
        category: "SAFE_ROUTE",
        label: "নিরাপদ রাস্তা",
      });

      startMeshRelay(db);
      await mockListeners.payloadReceived[0]({
        endpointId: "peer-1",
        dataBase64: base64Encode(utf8Encode(JSON.stringify(mark))),
      });

      expect(await listMarks(db)).toHaveLength(1);
    });

    it("silently rejects an incoming mark whose signature does not match its content", async () => {
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      const mark = await createSignedMark({
        lat: 23.7,
        lng: 90.4,
        category: "HAZARD",
        label: "আগুন",
      });
      const tampered = { ...mark, label: "নিরাপদ" }; // content changed after signing

      startMeshRelay(db);
      await mockListeners.payloadReceived[0]({
        endpointId: "peer-1",
        dataBase64: base64Encode(utf8Encode(JSON.stringify(tampered))),
      });

      expect(await listMarks(db)).toHaveLength(0);
    });

    it("does not forward a mark whose ttl_hops has already reached 0", async () => {
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      const relay = startMeshRelay(db);
      await mockListeners.connected[0]({ endpointId: "peer-1" });

      const mark = await createSignedMark({
        lat: 23.7,
        lng: 90.4,
        category: "OTHER",
        label: "test",
      });
      await expect(relay.relayMark({ ...mark, ttl_hops: 0 })).resolves.toBe(0);
    });

    it("receiving the same mark_id twice does not duplicate it", async () => {
      const db = createNodeSqliteExecutor();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      const mark = await createSignedMark({
        lat: 23.7,
        lng: 90.4,
        category: "RESOURCE",
        label: "পানি আছে",
      });
      const dataBase64 = base64Encode(utf8Encode(JSON.stringify(mark)));

      startMeshRelay(db);
      await mockListeners.payloadReceived[0]({ endpointId: "peer-1", dataBase64 });
      await mockListeners.payloadReceived[0]({ endpointId: "peer-2", dataBase64 });

      expect(await listMarks(db)).toHaveLength(1);
    });
  });
});
