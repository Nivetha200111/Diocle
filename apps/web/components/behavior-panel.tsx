"use client";

import { FileText } from "lucide-react";
import { downloadFile } from "@/lib/demo";
import type { Behavior, BehaviorClaim, ClaimExample, ClaimStatus, FieldValues } from "@/lib/runs";
import { Badge } from "./ui";

// Verified documentation: claims a model wrote about the ORIGINAL COBOL, each checked by running GnuCOBOL on its examples.
// The model proposes; GnuCOBOL decides. Wording rule: "confirmed on the examples tried", never "proven".

const TONE: Record<ClaimStatus, string> = { confirmed: "green", refuted: "amber", unchecked: "neutral" };
const LABEL: Record<ClaimStatus, string> = { confirmed: "CONFIRMED", refuted: "REFUTED", unchecked: "UNCHECKED" };
const EXAMPLE_LABEL = { matched: "MATCHED", differed: "DIFFERED", unchecked: "UNCHECKED" } as const;

const fields = (v: FieldValues) => Object.entries(v).map(([k, x]) => `${k}=${x}`).join("  ");

function expectedLines(e: ClaimExample["expected"]): string[] {
  const lines = (e.records ?? []).map((r, i) => `record ${i + 1}: ${fields(r)}`);
  if (e.outputRecordCount !== undefined) lines.push(`${e.outputRecordCount} output record(s)`);
  if (e.stdoutContains) lines.push(`stdout contains "${e.stdoutContains}"`);
  if (e.returnCode !== undefined) lines.push(`return code ${e.returnCode}`);
  return lines;
}

function actualLines(a: NonNullable<ClaimExample["actual"]>, shown: number): string[] {
  const lines = (a.records ?? []).slice(0, Math.max(shown, 1)).map((r, i) => `record ${i + 1}: ${fields(r)}`);
  if (a.outputRecordCount !== undefined) lines.push(`${a.outputRecordCount} output record(s)`);
  if (a.returnCode !== undefined && a.returnCode !== null) lines.push(`return code ${a.returnCode}`);
  return lines;
}

export function behaviorMarkdown(b: Behavior): string {
  const s = b.summary;
  const out = [
    `# Behaviour spec: ${b.program}`,
    "",
    `${s.confirmed} of ${s.claims} claims confirmed on the examples tried (${s.refuted} refuted, ${s.unchecked} unchecked).`,
    "",
    `Written by ${b.model}; every example was run on the original COBOL (${b.checkedWith}). GnuCOBOL decided, not the model. ` +
      `"Confirmed" means the examples tried matched, not that the claim is proven.`,
    "",
  ];
  if (b.skipped) return [...out, `Not written: ${b.skipped}`, ""].join("\n");
  for (const c of b.claims) {
    out.push(`## ${c.id} [${LABEL[c.status]}] ${c.statement}`, "");
    if (c.reason) out.push(`Unchecked: ${c.reason}`, "");
    for (const e of c.examples) {
      out.push(`- ${e.id} [${EXAMPLE_LABEL[e.status]}]`);
      out.push(`  - input: ${e.inputs.map(fields).join(" | ")}`);
      out.push(`  - expected: ${expectedLines(e.expected).join("; ")}`);
      if (e.actual) out.push(`  - actual (GnuCOBOL): ${actualLines(e.actual, (e.expected.records ?? []).length).join("; ")}`);
      for (const m of e.mismatches ?? []) out.push(`  - differed at ${m.what}: expected ${m.expected}, GnuCOBOL produced ${m.actual}`);
      if (e.reason) out.push(`  - unchecked: ${e.reason}`);
    }
    out.push("");
  }
  return out.join("\n");
}

function Example({ e }: { e: ClaimExample }) {
  return (
    <tr>
      <td className="mono">{e.id}<br /><Badge tone={e.status === "matched" ? "green" : e.status === "differed" ? "amber" : "neutral"} dot={false}>{EXAMPLE_LABEL[e.status]}</Badge></td>
      <td className="mono">{e.inputs.map((r, i) => <div key={i}>{fields(r)}</div>)}</td>
      <td className="mono">{expectedLines(e.expected).map((l, i) => <div key={i}>{l}</div>)}</td>
      <td className="mono">
        {e.actual
          ? actualLines(e.actual, (e.expected.records ?? []).length).map((l, i) => <div key={i}>{l}</div>)
          : <span>not run</span>}
        {(e.mismatches ?? []).map((m, i) => (
          <div key={`m${i}`}><strong>differed at {m.what}:</strong> expected {m.expected}, GnuCOBOL produced {m.actual}</div>
        ))}
        {e.reason && <div>{e.reason}</div>}
      </td>
    </tr>
  );
}

function Claim({ c }: { c: BehaviorClaim }) {
  return (
    <div className="claim" data-claim-status={c.status}>
      <p>
        <Badge tone={TONE[c.status]} dot={false}>{LABEL[c.status]}</Badge>{" "}
        <strong>{c.id}</strong> {c.statement}
      </p>
      {c.reason && <p><small>{c.reason}</small></p>}
      {c.examples.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Example</th><th>Input record(s)</th><th>The claim expects</th><th>GnuCOBOL produced</th></tr></thead>
            <tbody>{c.examples.map((e) => <Example key={e.id} e={e} />)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function BehaviorPanel({ b }: { b: Behavior }) {
  if (b.skipped) return null; // the trace and the model card already say why it did not run
  const s = b.summary;
  return (
    <section className={`panel breaker-panel ${s.refuted ? "breaker-broke" : ""}`}>
      <div className="panel-heading">
        <div>
          <h2><FileText size={14} /> Behaviour spec · verified documentation</h2>
          <p>
            <strong>{s.confirmed} of {s.claims} claims confirmed on the examples tried</strong>
            {" "}({s.refuted} refuted, {s.unchecked} unchecked; {s.examplesRun} examples run).{" "}
            {b.model} wrote the claims; the original COBOL, compiled with {b.checkedWith}, decided each one. The model did not.
            A refuted claim is kept and shown with what the COBOL actually produced.
          </p>
        </div>
        <button type="button" className="button" onClick={() => downloadFile(`${b.program}-behaviour-spec.md`, behaviorMarkdown(b), "text/markdown")}>
          Download as Markdown
        </button>
      </div>
      {b.claims.map((c) => <Claim key={c.id} c={c} />)}
    </section>
  );
}
