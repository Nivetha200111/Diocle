"use client";

import { FileText } from "lucide-react";
import { downloadFile } from "@/lib/demo";
import type { Behavior, BehaviorClaim, ClaimExample, ClaimStatus } from "@/lib/runs";
import { Badge } from "./ui";
import { actualLines, behaviorMarkdown, expectedLines, fields, flat } from "@/lib/behavior-markdown";

export { behaviorMarkdown };

// Verified documentation: claims a model wrote about the ORIGINAL COBOL, each checked by running GnuCOBOL on its examples.
// The model proposes; GnuCOBOL decides. Wording rule: "confirmed on the examples tried", never "proven".

const LABEL: Record<ClaimStatus, string> = { confirmed: "CONFIRMED", refuted: "REFUTED", unchecked: "UNCHECKED" };
const EXAMPLE_LABEL = { matched: "MATCHED", differed: "DIFFERED", unchecked: "UNCHECKED" } as const;
const tone = (s: string | undefined) => (s === "confirmed" || s === "matched" ? "green" : s === "refuted" || s === "differed" ? "amber" : "neutral");

// Every field is read defensively: a partial or older `behavior` object must render, not crash the run view.
function Example({ e }: { e: ClaimExample }) {
  const shown = (e.expected?.records ?? []).length;
  return (
    <tr>
      <td className="mono">{e.id}<br /><Badge tone={tone(e.status)} dot={false}>{EXAMPLE_LABEL[e.status] ?? "UNCHECKED"}</Badge></td>
      <td className="mono">{(e.inputs ?? []).map((r, i) => <div key={i}>{fields(r)}</div>)}</td>
      <td className="mono">{expectedLines(e.expected).map((l, i) => <div key={i}>{l}</div>)}</td>
      <td className="mono">
        {e.actual
          ? actualLines(e.actual, shown).map((l, i) => <div key={i}>{l}</div>)
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
  const examples = c.examples ?? [];
  return (
    <div className="claim" data-claim-status={c.status}>
      <p>
        <Badge tone={tone(c.status)} dot={false}>{LABEL[c.status] ?? "UNCHECKED"}</Badge>{" "}
        <strong>{c.id}</strong> {c.statement}
      </p>
      {c.reason && <p><small>{c.reason}</small></p>}
      {examples.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Example</th><th>Input record(s)</th><th>The claim expects</th><th>GnuCOBOL produced</th></tr></thead>
            <tbody>{examples.map((e, i) => <Example key={e.id ?? i} e={e} />)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function BehaviorPanel({ b }: { b: Partial<Behavior> }) {
  if (b.skipped) return null; // the trace and the model card already say why it did not run
  const s = { claims: 0, confirmed: 0, refuted: 0, unchecked: 0, examplesRun: 0, ...(b.summary ?? {}) };
  return (
    <section className={`panel ${s.refuted ? "behavior-refuted" : ""}`}>
      <div className="panel-heading">
        <div>
          <h2><FileText size={14} /> Behaviour spec · verified documentation</h2>
          <p>
            <strong>{s.confirmed} of {s.claims} claims confirmed on the examples tried</strong>
            {" "}({s.refuted} refuted, {s.unchecked} unchecked; {s.examplesRun} examples run).{" "}
            {b.model ?? "A model"} wrote the claims; the original COBOL, compiled with {b.checkedWith ?? "GnuCOBOL"}, decided each one. The model did not.
            Confirmed means the examples&apos; stated expectations held on GnuCOBOL; the sentence itself is not machine-checked.
            A refuted claim is kept and shown with what the COBOL actually produced.
          </p>
        </div>
        <button type="button" className="button" onClick={() => downloadFile(`${flat(b.program ?? "program", 60)}-behaviour-spec.md`, behaviorMarkdown(b), "text/markdown")}>
          Download as Markdown
        </button>
      </div>
      {(b.claims ?? []).map((c, i) => <Claim key={c.id ?? i} c={c} />)}
    </section>
  );
}
