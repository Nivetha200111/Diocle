// What the Database comparison panel shows, as plain strings. The panel renders ONLY these strings, so odd engine output
// (numbers, objects, huge strings, null) can never crash it; scripts/check-database-view.mts feeds it exactly that.
// Every value is capped at 200 characters; objects are shown as short JSON; anything unreadable shows as "invalid".

export const cap = (v: unknown): string => {
  let s: string;
  if (v == null) s = "";
  else if (typeof v === "string") s = v;
  else if (typeof v === "number" || typeof v === "boolean" || typeof v === "bigint") s = String(v);
  else {
    try { s = JSON.stringify(v) ?? "invalid"; } catch { s = "invalid"; }
  }
  return s.length > 200 ? `${s.slice(0, 200)}…` : s;
};
const num = (v: unknown): string => (typeof v === "number" && Number.isFinite(v) ? String(v) : "n/a");
const changedText = (v: unknown): string => (v === true ? "yes" : v === false ? "no" : "unknown");

export type DbRow = {
  name: string; seeded: string; after: string; changed: string;
  status: "MATCH" | "DIFFERS" | "NOT COMPARED"; match: boolean;
  mismatch: { row: string; column: string; original: string; converted: string } | null;
};
export type DbView = { engine: string; subset: string; seededFrom: string; bad: boolean; rows: DbRow[] };

export function databaseView(d: unknown): DbView | null {
  if (!d || typeof d !== "object") return null;
  const o = d as Record<string, unknown>;
  const tables = Array.isArray(o.tables) ? o.tables : [];
  if (tables.length === 0) return null;
  const rows: DbRow[] = tables.map((raw) => {
    const t = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
    const ch = (t.changedFromSeed && typeof t.changedFromSeed === "object" ? t.changedFromSeed : {}) as Record<string, unknown>;
    const m = t.firstMismatch && typeof t.firstMismatch === "object" ? (t.firstMismatch as Record<string, unknown>) : null;
    const match = t.match === true;
    return {
      name: t.name == null ? "unnamed" : cap(t.name),
      seeded: num(t.rowsSeeded),
      after: `${num(t.rowsOriginal)} / ${num(t.rowsConverted)}`,
      changed: `${changedText(ch.original)} / ${changedText(ch.converted)}`,
      status: match ? "MATCH" : t.match === false ? "DIFFERS" : "NOT COMPARED",
      match,
      mismatch: m ? { row: num(m.row), column: cap(m.column), original: cap(m.original), converted: cap(m.converted) } : null,
    };
  });
  const engine = [o.engine == null ? "unknown" : cap(o.engine), o.engineVersion == null ? "" : cap(o.engineVersion)].join(" ").trim();
  return {
    engine, subset: o.subset == null ? "unknown" : cap(o.subset), seededFrom: o.seededFrom == null ? "unknown" : cap(o.seededFrom),
    bad: rows.some((r) => !r.match), rows,
  };
}
