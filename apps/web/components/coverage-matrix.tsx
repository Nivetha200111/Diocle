import { Badge } from "./ui";

// What Diocle can and cannot verify today, by kind of mainframe artifact. Static, dated, and kept honest: a row says "in progress"
// until the work is merged and deployed. Status as of Oct 30, 2026.
type Row = { area: string; status: "verified" | "subset" | "partial" | "progress" | "none"; checked: string; limit: string };

const ROWS: Row[] = [
  { area: "Sequential files (QSAM-style)", status: "verified", checked: "Outputs compared byte for byte, original on GnuCOBOL against the Java, plus 1,000 held-out inputs.", limit: "On the inputs tried." },
  { area: "Copybooks (COPY, REPLACING)", status: "verified", checked: "Record layouts come from the copybooks; verification and SQL schemas are derived from them.", limit: "Copybooks outside the repository refuse the program with a reason." },
  { area: "Static CALLs between programs", status: "verified", checked: "Called programs are translated together and linked into one executable.", limit: "Dynamic CALLs and calls to programs not in the repository are refused." },
  { area: "JCL jobs", status: "partial", checked: "One SORT step feeding one COBOL step, with DD overrides: every final dataset compared.", limit: "Longer jobs, several SORT steps, COND-gated steps and IDCAMS are refused with a reason." },
  { area: "Embedded SQL (DB2)", status: "subset", checked: "A named subset (SELECT INTO, INSERT, UPDATE, DELETE, cursors, COMMIT, ROLLBACK, SQLCODE) with final table contents compared.", limit: "Verified on a SQLite stand-in, never on real DB2. Dynamic SQL, joins and DB2-only clauses are refused." },
  { area: "Keyed files (VSAM KSDS-style)", status: "progress", checked: "Being built: a keyed-file subset compared by key order on GnuCOBOL's indexed-file handler.", limit: "Refused today. Not merged or deployed yet." },
  { area: "Whole-repository build check", status: "progress", checked: "Being built: compile every converted program together, flag copybook drift and CALL signature mismatches.", limit: "Each program is compiled and verified on its own today. Not merged or deployed yet." },
  { area: "Hierarchical database (IMS DL/I)", status: "none", checked: "Not supported: there is no free IMS runtime to compare against.", limit: "On the roadmap." },
  { area: "CICS online transactions", status: "none", checked: "Not supported.", limit: "Programs with EXEC CICS are refused with a reason." },
];

const LABEL: Record<Row["status"], [string, string]> = {
  verified: ["VERIFIED", "green"], subset: ["SUBSET", "green"], partial: ["PARTIAL", "amber"], progress: ["IN PROGRESS", "amber"], none: ["NOT SUPPORTED", "red"],
};

// The shared table style does not wrap cells; these two columns hold sentences.
const WRAP = { whiteSpace: "normal", verticalAlign: "top", minWidth: 220 } as const;

export default function CoverageMatrix() {
  return (
    <section className="panel" aria-labelledby="coverage-heading">
      <div className="panel-heading">
        <div>
          <h2 id="coverage-heading">What Diocle verifies today, and what it does not</h2>
          <p>By kind of mainframe artifact, as of Oct 30, 2026. In progress means not merged or deployed yet. Certified always means on the inputs tried.</p>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <caption className="sr-only">Coverage by kind of mainframe artifact</caption>
          <thead>
            <tr><th scope="col">Artifact</th><th scope="col">Status</th><th scope="col">What is checked</th><th scope="col">Limit</th></tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.area}>
                <th scope="row">{r.area}</th>
                <td><Badge tone={LABEL[r.status][1]}>{LABEL[r.status][0]}</Badge></td>
                <td style={WRAP}>{r.checked}</td>
                <td style={WRAP}>{r.limit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
