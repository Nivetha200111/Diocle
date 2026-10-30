"use client";

// The assurance label of a convert-anyway program or run (contracts/run.schema.json `assurance`). The reason shows on hover
// (title) and, for a run, in the note below. Nothing here ever says "certified" of an unverified program.
import { ASSURANCE_BADGE, type Assurance, type CobolRepair } from "@/lib/runs";
import { Badge } from "./ui";

export function AssuranceBadge({ assurance, reason }: { assurance: Assurance; reason?: string | null }) {
  const b = ASSURANCE_BADGE[assurance];
  return (
    <span title={reason ?? undefined} className="assurance-badge" data-assurance={assurance}>
      <Badge tone={b.tone}>{b.label}</Badge>
    </span>
  );
}

const MEANING: Record<Assurance, string> = {
  certified: "The differential test passed against the original COBOL.",
  "certified-against-repaired-cobol": "The original did not compile under GnuCOBOL, so it was patched; the differential test passed against the PATCHED COBOL, not the original.",
  "compiled-unverified": "The Java compiles with javac. No differential test ran and the Java was never executed. A developer must review it.",
  failed: "No compiling Java was produced within the caps, or the differential test ran and the Java differs.",
};

export function AssuranceNote({ assurance, reason, repair }: { assurance: Assurance; reason?: string | null; repair?: CobolRepair | null }) {
  if (assurance === "certified") return null;
  return (
    <section className="panel assurance-note">
      <div className="panel-heading">
        <div>
          <h2>Not certified: {ASSURANCE_BADGE[assurance].label.toLowerCase()}</h2>
          <p>{MEANING[assurance]}</p>
        </div>
      </div>
      {reason && <p className="assurance-reason">{reason}</p>}
      {repair && (
        <details className="assurance-diff">
          <summary>
            COBOL patch: {repair.changedLines} line(s) changed by {repair.method === "model" ? "Muse" : "a fixed mechanical rule"}
            {repair.fixes?.length ? ` (${repair.fixes.join("; ")})` : ""}
          </summary>
          {repair.diagnostics.length > 0 && <pre className="mono">{repair.diagnostics.join("\n")}</pre>}
          <pre className="mono diff">{repair.diff || "(no diff recorded)"}</pre>
        </details>
      )}
    </section>
  );
}
