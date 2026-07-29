import { getReportQueueDatabase } from "./executor";
import type { SqliteExecutor } from "./executor";
import { initReportQueueSchema } from "./queue";

let initialized: Promise<SqliteExecutor> | null = null;

/** Lazily opens (once) and schema-initializes the single on-device report
 * queue shared by the SOS form, the mesh relay, sync, and the my-reports
 * view. */
export function getAppDatabase(): Promise<SqliteExecutor> {
  if (!initialized) {
    initialized = (async () => {
      const db = getReportQueueDatabase();
      await initReportQueueSchema(db);
      return db;
    })();
  }
  return initialized;
}
