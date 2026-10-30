import { Database } from "lucide-react";
import type { DatabaseComparison, DatabaseTable } from "@/lib/runs";
import { Badge } from "./ui";

// Database comparison for EXEC SQL runs (verification-report v0.9). Every field is read defensively: a partial or older
// object must render (or render nothing), never crash the run view. All strings are rendered as React text (escaped).

const n = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? String(v) : "n/a");
const changed = (v: boolean | undefined) => (v === true ? "yes" : v === false ? "no" : "unknown");
// A mismatch value is verifier output about database contents; cap its length so one huge cell cannot blow up the page.
const cap = (v: unknown) => { const s = String(v ?? ""); return s.length > 200 ? `${s.slice(0, 200)}…` : s; };

function mismatch(t: DatabaseTable) {
  const m = t.firstMismatch;
  if (!m || typeof m !== "object") return null;
  return (
    <div>
      <strong>First difference:</strong> row {n(m.row)}, column <span className="mono">{cap(m.column)}</span>:
      {" "}COBOL <span className="mono">{cap(m.original)}</span>, Java <span className="mono">{cap(m.converted)}</span>
    </div>
  );
}

export function DatabasePanel({ d }: { d: DatabaseComparison }) {
  const tables = Array.isArray(d?.tables) ? d.tables : [];
  if (!d || typeof d !== "object" || tables.length === 0) return null;
  const bad = tables.some((t) => t?.match !== true);
  return (
    <section className={`panel db-panel ${bad ? "db-failing" : ""}`} aria-labelledby="db-compare-heading">
      <div className="panel-heading">
        <div>
          <h2 id="db-compare-heading"><Database size={14} /> Database comparison (SQLite stand-in)</h2>
          <p>
            The COBOL and the Java ran on identically seeded databases; final contents of every table were compared value for value.
            The engine is SQLite standing in for DB2: equivalent on this engine, for these statements, on the inputs tried. Not DB2-verified.
          </p>
          <p>
            <strong>Engine:</strong> {d.engine ?? "unknown"} {d.engineVersion ?? ""} · <strong>SQL subset:</strong> {d.subset ?? "unknown"} ·{" "}
            <strong>Seeded from:</strong> {d.seededFrom ?? "unknown"}
          </p>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Final table contents, COBOL against Java</caption>
          <thead>
            <tr>
              <th scope="col">Table</th><th scope="col">Rows seeded</th><th scope="col">Rows after (COBOL / Java)</th>
              <th scope="col">Changed from seed (COBOL / Java)</th><th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            {tables.map((t, i) => (
              <tr key={i} className={t?.match === true ? "" : "db-row-failing"}>
                <th scope="row" className="mono">{t?.name ?? "unnamed"}</th>
                <td>{n(t?.rowsSeeded)}</td>
                <td>{n(t?.rowsOriginal)} / {n(t?.rowsConverted)}</td>
                <td>{changed(t?.changedFromSeed?.original)} / {changed(t?.changedFromSeed?.converted)}</td>
                <td>
                  {t?.match === true ? <Badge tone="green">MATCH</Badge> : <Badge tone="amber">{t?.match === false ? "DIFFERS" : "NOT COMPARED"}</Badge>}
                  {mismatch(t ?? {})}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
