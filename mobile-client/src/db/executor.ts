import { open } from "@op-engineering/op-sqlite";

export type SqliteScalar = string | number | null;
export type SqliteRow = Record<string, SqliteScalar>;

/** Minimal surface queue.ts depends on. Kept narrow and separate from
 * op-sqlite's full DB type so tests can inject a real (non-mocked) SQLite
 * engine — see db/__tests__/queue.test.ts, which runs the actual queue SQL
 * against Node's built-in node:sqlite rather than a hand-rolled fake. */
export type SqliteExecutor = {
  execute: (sql: string, params?: SqliteScalar[]) => Promise<{ rows: SqliteRow[]; rowsAffected: number }>;
};

let dbSingleton: SqliteExecutor | null = null;

export function getReportQueueDatabase(): SqliteExecutor {
  if (dbSingleton) return dbSingleton;
  const db = open({ name: "protidhoni_queue.db" });
  dbSingleton = {
    execute: async (sql, params) => {
      const result = await db.execute(sql, params);
      return { rows: (result.rows ?? []) as SqliteRow[], rowsAffected: result.rowsAffected };
    },
  };
  return dbSingleton;
}
