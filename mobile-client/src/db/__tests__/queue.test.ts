import type { CrisisReport } from "../../contracts/report";
import {
  enqueueReport,
  hasReport,
  initReportQueueSchema,
  listAllReports,
  listUnsyncedReports,
  updateSyncStatus,
} from "../queue";
import { createNodeSqliteExecutor } from "../testSupport/nodeSqliteExecutor";

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

async function freshDb() {
  const db = createNodeSqliteExecutor();
  await initReportQueueSchema(db);
  return db;
}

describe("report queue", () => {
  it("enqueues a new report as 'inserted'", async () => {
    const db = await freshDb();
    expect(await enqueueReport(db, makeReport())).toBe("inserted");
  });

  it("enqueuing the same message_id again is a no-op ('duplicate')", async () => {
    const db = await freshDb();
    const report = makeReport();
    expect(await enqueueReport(db, report)).toBe("inserted");
    expect(await enqueueReport(db, report)).toBe("duplicate");

    const all = await listAllReports(db);
    expect(all).toHaveLength(1);
  });

  it("hasReport reflects what has actually been stored", async () => {
    const db = await freshDb();
    expect(await hasReport(db, "11111111-1111-4111-8111-111111111111")).toBe(false);
    await enqueueReport(db, makeReport());
    expect(await hasReport(db, "11111111-1111-4111-8111-111111111111")).toBe(true);
  });

  it("listUnsyncedReports excludes synced reports", async () => {
    const db = await freshDb();
    await enqueueReport(db, makeReport({ message_id: "a0000000-0000-4000-8000-000000000001" }));
    await enqueueReport(
      db,
      makeReport({ message_id: "a0000000-0000-4000-8000-000000000002", sync_status: "synced" }),
    );

    const unsynced = await listUnsyncedReports(db);
    expect(unsynced.map((r) => r.message_id)).toEqual(["a0000000-0000-4000-8000-000000000001"]);
  });

  it("updateSyncStatus overlays the live column value onto the returned report", async () => {
    const db = await freshDb();
    const report = makeReport();
    await enqueueReport(db, report);

    await updateSyncStatus(db, report.message_id, "relayed");

    const [stored] = await listAllReports(db);
    expect(stored.sync_status).toBe("relayed");
  });

  it("updateSyncStatus never downgrades an already-synced report", async () => {
    const db = await freshDb();
    const report = makeReport();
    await enqueueReport(db, report);
    await updateSyncStatus(db, report.message_id, "synced");

    await updateSyncStatus(db, report.message_id, "relayed");

    const [stored] = await listAllReports(db);
    expect(stored.sync_status).toBe("synced");
  });

  it("updateSyncStatus on an unknown message_id is a harmless no-op", async () => {
    const db = await freshDb();
    await expect(updateSyncStatus(db, "does-not-exist", "synced")).resolves.toBeUndefined();
  });

  it("listAllReports orders most-recently-queued first", async () => {
    const db = await freshDb();
    await enqueueReport(db, makeReport({ message_id: "a0000000-0000-4000-8000-000000000001" }));
    await new Promise((resolve) => setTimeout(resolve, 5));
    await enqueueReport(db, makeReport({ message_id: "a0000000-0000-4000-8000-000000000002" }));

    const all = await listAllReports(db);
    expect(all.map((r) => r.message_id)).toEqual([
      "a0000000-0000-4000-8000-000000000002",
      "a0000000-0000-4000-8000-000000000001",
    ]);
  });
});
