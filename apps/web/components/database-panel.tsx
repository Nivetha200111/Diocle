import { Database } from "lucide-react";
import type { DatabaseComparison } from "@/lib/runs";
import { databaseView } from "@/lib/database-view";
import { Badge } from "./ui";

// Database comparison for EXEC SQL runs (verification-report v0.9). Every field is read defensively: a partial or older
// object must render (or render nothing), never crash the run view. All strings are rendered as React text (escaped).

export function DatabasePanel({ d }: { d: DatabaseComparison }) {
  const v = databaseView(d);
  if (!v) return null;
  return (
    <section className={`panel db-panel ${v.bad ? "db-failing" : ""}`} aria-labelledby="db-compare-heading">
      <div className="panel-heading">
        <div>
          <h2 id="db-compare-heading"><Database size={14} /> Database comparison (SQLite stand-in)</h2>
          <p>
            The COBOL and the Java ran on identically seeded databases; final contents of every table were compared value for value.
            The engine is SQLite standing in for DB2: equivalent on this engine, for these statements, on the inputs tried. Not DB2-verified.
          </p>
          <p>
            <strong>Engine:</strong> {v.engine} · <strong>SQL subset:</strong> {v.subset} ·{" "}
            <strong>Seeded from:</strong> {v.seededFrom}
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
            {v.rows.map((r, i) => (
              <tr key={i} className={r.match ? "" : "db-row-failing"}>
                <th scope="row" className="mono">{r.name}</th>
                <td>{r.seeded}</td>
                <td>{r.after}</td>
                <td>{r.changed}</td>
                <td>
                  <Badge tone={r.status === "MATCH" ? "green" : "amber"}>{r.status}</Badge>
                  {r.mismatch && (
                    <div>
                      <strong>First difference:</strong> row {r.mismatch.row}, column <span className="mono">{r.mismatch.column}</span>:
                      {" "}COBOL <span className="mono">{r.mismatch.original}</span>, Java <span className="mono">{r.mismatch.converted}</span>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
