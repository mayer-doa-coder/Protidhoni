import { getReportQueueDatabase } from "./executor";
import type { SqliteExecutor } from "./executor";
import { initMapMarkSchema } from "./marks";
import { initReportQueueSchema } from "./queue";

let initialized: Promise<SqliteExecutor> | null = null;

/** Lazily opens (once) and schema-initializes the single on-device database
 * shared by the report forms, the mesh relay, sync, the my-reports view, and
 * the offline map's marks. */
export function getAppDatabase(): Promise<SqliteExecutor> {
  if (!initialized) {
    initialized = (async () => {
      const db = getReportQueueDatabase();
      await initReportQueueSchema(db);
      await initMapMarkSchema(db);
      return db;
    })();
  }
  return initialized;
}
