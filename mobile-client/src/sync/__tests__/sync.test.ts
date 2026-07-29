import type { CrisisReport } from "../../contracts/report";
import {
  enqueueReport,
  initReportQueueSchema,
  listReportRecords,
  listUnsyncedReports,
} from "../../db/queue";
import { createNodeSqliteExecutor } from "../../db/testSupport/nodeSqliteExecutor";

type NetInfoListener = (state: { isConnected: boolean | null; isInternetReachable: boolean | null }) => void;

// Same self-contained-factory pattern as mesh/__tests__/relay.test.ts — see
// the comment there for why closing over an outer `mock`-prefixed variable
// is unsafe here (ES import hoisting can run the factory before that
// variable is assigned).
jest.mock("@react-native-community/netinfo", () => {
  const listeners: NetInfoListener[] = [];
  const unsubscribe = jest.fn();
  return {
    __esModule: true,
    default: {
      addEventListener: jest.fn((listener: NetInfoListener) => {
        listeners.push(listener);
        return unsubscribe;
      }),
      __mockListeners: listeners,
      __mockUnsubscribe: unsubscribe,
    },
  };
});

import NetInfo from "@react-native-community/netinfo";
import { startAutoSync, syncQueueToBackend } from "../sync";

type MockedNetInfo = typeof NetInfo & {
  __mockListeners: NetInfoListener[];
  __mockUnsubscribe: jest.Mock;
};
const mockNetInfoListeners = (NetInfo as MockedNetInfo).__mockListeners;
const mockNetInfoUnsubscribe = (NetInfo as MockedNetInfo).__mockUnsubscribe;

const config = { apiBaseUrl: "http://backend.test" };

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

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500): Response {
  return { ok, status, json: async () => body } as Response;
}

describe("syncQueueToBackend", () => {
  beforeEach(() => {
    mockNetInfoListeners.length = 0;
    mockNetInfoUnsubscribe.mockClear();
    global.fetch = jest.fn();
  });

  it("does nothing when the queue is empty", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);

    await syncQueueToBackend(db, config);

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("POSTs the queue and marks accepted/duplicate reports as synced", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport({ message_id: "a0000000-0000-4000-8000-000000000001" }));
    await enqueueReport(db, makeReport({ message_id: "a0000000-0000-4000-8000-000000000002" }));

    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse({
        results: [
          { message_id: "a0000000-0000-4000-8000-000000000001", outcome: "accepted" },
          { message_id: "a0000000-0000-4000-8000-000000000002", outcome: "duplicate" },
        ],
      }),
    );

    await syncQueueToBackend(db, config);

    expect(global.fetch).toHaveBeenCalledWith(
      "http://backend.test/reports",
      expect.objectContaining({ method: "POST" }),
    );
    expect(await listUnsyncedReports(db)).toHaveLength(0);
    const records = await listReportRecords(db);
    expect(records.map(record => record.deliveryOutcome).sort()).toEqual(["accepted", "duplicate"]);
  });

  it("leaves a rejected report queued (unsynced)", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse({ results: [{ message_id: "11111111-1111-4111-8111-111111111111", outcome: "rejected" }] }),
    );

    await syncQueueToBackend(db, config);

    expect(await listUnsyncedReports(db)).toHaveLength(1);
    const [record] = await listReportRecords(db);
    expect(record.deliveryOutcome).toBe("rejected");
    expect(record.deliveryFeedback).toContain("rejected");
  });

  it("leaves the queue untouched when the backend is unreachable", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    (global.fetch as jest.Mock).mockRejectedValue(new Error("network error"));

    await syncQueueToBackend(db, config);

    expect(await listUnsyncedReports(db)).toHaveLength(1);
    const [record] = await listReportRecords(db);
    expect(record.deliveryFeedback).toContain("unreachable");
  });

  it("leaves the queue untouched on a non-2xx response", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    (global.fetch as jest.Mock).mockResolvedValue(jsonResponse({}, false, 503));

    await syncQueueToBackend(db, config);

    expect(await listUnsyncedReports(db)).toHaveLength(1);
    const [record] = await listReportRecords(db);
    expect(record.deliveryFeedback).toContain("HTTP 503");
  });

  it("records unreadable and structurally invalid success responses", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    (global.fetch as jest.Mock).mockResolvedValueOnce({
      ok: true,
      status: 202,
      json: async () => {
        throw new SyntaxError("invalid JSON");
      },
    } as unknown as Response);
    await syncQueueToBackend(db, config);
    let [record] = await listReportRecords(db);
    expect(record.deliveryFeedback).toContain("unreadable");

    (global.fetch as jest.Mock).mockResolvedValueOnce(jsonResponse({ results: [{ bad: true }] }));
    await syncQueueToBackend(db, config);
    [record] = await listReportRecords(db);
    expect(record.deliveryFeedback).toContain("incomplete");
  });

  it("keeps a report queued when the success response omits its message_id", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());
    (global.fetch as jest.Mock).mockResolvedValue(jsonResponse({ results: [] }));

    await syncQueueToBackend(db, config);

    const [record] = await listReportRecords(db);
    expect(record.report.sync_status).toBe("local");
    expect(record.deliveryFeedback).toContain("omitted");
  });

  it("splits more than 100 queued reports into multiple batched requests", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    for (let i = 0; i < 120; i++) {
      const id = `b${String(i).padStart(7, "0")}-0000-4000-8000-000000000000`;
      await enqueueReport(db, makeReport({ message_id: id }));
    }

    (global.fetch as jest.Mock).mockImplementation(async (_url: string, init: { body: string }) => {
      const body = JSON.parse(init.body) as { reports: CrisisReport[] };
      return jsonResponse({
        results: body.reports.map((r) => ({ message_id: r.message_id, outcome: "accepted" })),
      });
    });

    await syncQueueToBackend(db, config);

    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(await listUnsyncedReports(db)).toHaveLength(0);
  });
});

describe("startAutoSync", () => {
  beforeEach(() => {
    mockNetInfoListeners.length = 0;
    mockNetInfoUnsubscribe.mockClear();
    global.fetch = jest.fn().mockResolvedValue(jsonResponse({ results: [] }));
  });

  it("triggers a sync when connectivity with internet reachability is (re)gained", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    startAutoSync(db, config);
    await mockNetInfoListeners[0]({ isConnected: true, isInternetReachable: true });
    await Promise.resolve();

    expect(global.fetch).toHaveBeenCalled();
  });

  it("does not trigger a sync while offline", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    startAutoSync(db, config);
    await mockNetInfoListeners[0]({ isConnected: false, isInternetReachable: false });

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("does not trigger a sync when connected but the internet is confirmed unreachable", async () => {
    const db = createNodeSqliteExecutor();
    await initReportQueueSchema(db);
    await enqueueReport(db, makeReport());

    startAutoSync(db, config);
    await mockNetInfoListeners[0]({ isConnected: true, isInternetReachable: false });

    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("returns NetInfo's own unsubscribe function", () => {
    const db = createNodeSqliteExecutor();
    const stop = startAutoSync(db, config);
    expect(stop).toBe(mockNetInfoUnsubscribe);
  });
});
