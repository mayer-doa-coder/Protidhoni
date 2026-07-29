import { DatabaseSync } from "node:sqlite";

import type { SqliteExecutor, SqliteRow, SqliteScalar } from "../executor";

/**
 * Test-only SqliteExecutor backed by Node's built-in `node:sqlite`. This lets
 * queue.test.ts run the actual SQL in queue.ts against a real SQLite engine
 * instead of a hand-rolled fake that could silently diverge from real SQL
 * semantics. Never imported from app code — op-sqlite (native, unavailable
 * outside a built Android/iOS app) is what actually ships.
 */
export function createNodeSqliteExecutor(): SqliteExecutor {
  const db = new DatabaseSync(":memory:");
  return {
    execute: async (sql: string, params: SqliteScalar[] = []) => {
      const stmt = db.prepare(sql);
      if (sql.trim().toUpperCase().startsWith("SELECT")) {
        const rows = stmt.all(...params) as unknown as SqliteRow[];
        return { rows, rowsAffected: 0 };
      }
      const result = stmt.run(...params);
      return { rows: [], rowsAffected: Number(result.changes) };
    },
  };
}
