import type { CrisisReport } from "../../contracts/report";
import {
  enqueueReport,
  hasReport,
  initReportQueueSchema,
  listAllReports,
  listReportRecords,
  listUnsyncedReports,
  recordDeliveryResult,
  recordSyncFailure,
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

  it("migrates a Phase 1 queue without deleting its reports", async () => {
    const db = createNodeSqliteExecutor();
    const report = makeReport();
    await db.execute(`
      CREATE TABLE report_queue (
        message_id TEXT PRIMARY KEY,
        report_json TEXT NOT NULL,
        sync_status TEXT NOT NULL,
        queued_at TEXT NOT NULL
      )
    `);
    await db.execute(
      `INSERT INTO report_queue (message_id, report_json, sync_status, queued_at) VALUES (?, ?, ?, ?)`,
      [report.message_id, JSON.stringify(report), "local", "2026-07-30T00:00:00.000Z"],
    );

    await initReportQueueSchema(db);

    const [record] = await listReportRecords(db);
    expect(record.report.message_id).toBe(report.message_id);
    expect(record.deliveryOutcome).toBeNull();
    expect(record.deliveryFeedback).toBeNull();
    expect(record.lastSyncAttemptAt).toBeNull();
  });

  it("persists accepted and duplicate delivery confirmation", async () => {
    const db = await freshDb();
    const accepted = makeReport({ message_id: "a0000000-0000-4000-8000-000000000001" });
    const duplicate = makeReport({ message_id: "a0000000-0000-4000-8000-000000000002" });
    await enqueueReport(db, accepted);
    await enqueueReport(db, duplicate);

    await recordDeliveryResult(db, accepted.message_id, "accepted", "2026-07-30T01:00:00.000Z");
    await recordDeliveryResult(db, duplicate.message_id, "duplicate", "2026-07-30T01:01:00.000Z");

    const records = await listReportRecords(db);
    expect(records.map(record => record.deliveryOutcome).sort()).toEqual(["accepted", "duplicate"]);
    expect(records.every(record => record.report.sync_status === "synced")).toBe(true);
  });

  it("keeps a rejected report queued with durable feedback", async () => {
    const db = await freshDb();
    const report = makeReport();
    await enqueueReport(db, report);

    await recordDeliveryResult(db, report.message_id, "rejected", "2026-07-30T02:00:00.000Z");

    const [record] = await listReportRecords(db);
    expect(record.report.sync_status).toBe("local");
    expect(record.deliveryOutcome).toBe("rejected");
    expect(record.deliveryFeedback).toContain("rejected");
    expect(await listUnsyncedReports(db)).toHaveLength(1);
  });

  it("records connectivity feedback without erasing an earlier rejection", async () => {
    const db = await freshDb();
    const report = makeReport();
    await enqueueReport(db, report);
    await recordDeliveryResult(db, report.message_id, "rejected", "2026-07-30T02:00:00.000Z");
    const [before] = await listReportRecords(db);

    await recordSyncFailure(
      db,
      [report.message_id],
      "Backend unreachable.",
      "2026-07-30T03:00:00.000Z",
    );

    const [after] = await listReportRecords(db);
    expect(after.deliveryFeedback).toBe(before.deliveryFeedback);
    expect(after.lastSyncAttemptAt).toBe("2026-07-30T03:00:00.000Z");
  });
});
