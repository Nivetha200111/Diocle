"use client";

import { KNOWN_DIFFERENCE } from "@/lib/config";
import { MessageSquareText } from "lucide-react";
import { hostOf, originalDidNotCompile, originalWroteNothing, type ModelCall, type Run } from "@/lib/runs";

// "In plain English": a card at the top of a run, built only from fields of the run record. Nothing is written about what
// the program does unless the run has a verified behaviour spec (claims a model wrote, then confirmed by running the
// original COBOL). Everything is rendered as text by React (never as HTML): claim text is model-written.

const MAX_CLAIMS = 5;
const MAX_CHARS = 280;
const n = (v: number) => v.toLocaleString("en-US");
const clip = (s: string, max: number) => (s.length > max ? `${s.slice(0, max - 1).trimEnd()}…` : s);
const money = (v: number | null | undefined) =>
  v === null || v === undefined ? null : `$${v < 0.01 ? v.toFixed(4) : v.toFixed(2)}`;

const ROLE_WORDS: Record<string, string> = {
  translator: "wrote the first Java", repair: "repaired it", breaker: "attacked it", crosscheck: "independent check",
  document: "wrote the claims above", guard: "reviewed the final Java",
};

// One honest sentence about the outcome, from the record's own status, counts and assurance.
export function verdictSentence(run: Run): string {
  if (run.status === "running") return "This run is still in progress; there is no verdict yet.";
  if (run.status === "interrupted") return "This run was cut off by an engine restart before it finished; there is no verdict.";
  const after = run.after;
  const counts = after && after.total > 0 ? `${n(after.passed)} of ${n(after.total)}` : null;
  const reported = run.visitor ? " (as reported by the import; not re-verified on this site)" : "";
  if (run.assurance === "compiled-unverified") return "The Java compiles, but no test ran: it is not verified and needs a developer's review.";
  if (run.assurance === "certified-against-repaired-cobol") {
    return `The original COBOL did not compile, so it was patched. The Java matched the PATCHED COBOL${counts ? ` on ${counts} held-out output records` : ""}; a person must confirm the patch keeps the original's meaning.`;
  }
  if (run.certified && counts) {
    const first = run.before && run.before.failed > 0
      ? ` Its first Java failed ${n(run.before.failed)} of ${n(run.before.total)} starting tests and was repaired.` : "";
    return `The Java matched the original COBOL on ${counts} held-out output records (one run of each program on generated inputs the repair agent never saw), byte for byte${after?.stdoutMatch === false ? ", except printed output" : ""}${reported}.${first} "Certified" means on the inputs tried, not proven for every input.`;
  }
  if (run.certified) return `Certified${reported}, but this record has no held-out input counts to quote.`;
  if (counts && after && after.failed === 0 && !after.stdoutMatch) return `Not certified: all ${counts} held-out output records matched, but the printed display output differed.`;
  if (counts) return `Not certified: the Java matched the original on only ${counts} held-out output records${after && originalWroteNothing(after) ? " (the original COBOL wrote no records on them)" : ""}.`;
  const why = run.error ? ` The run record says: ${clip(run.error.replace(/\s+/g, " "), 320)}` : "";
  if (originalDidNotCompile(run.error)) return `Not certified: the original COBOL did not compile, so nothing could be compared.${why}`;
  if (after) return `Not certified: no held-out input was compared (the Java did not build, or neither program wrote output).${why}`;
  return `Not certified: the run ended before a comparison could be made.${why}`;
}

export function breakerSentence(run: Run): string | null {
  const b = run.breaker;
  if (!b || !(b.tried > 0)) return null;
  if (b.broke === 0) return `A second AI (the breaker agent) ran ${n(b.tried)} inputs meant to make the Java differ; none did. That is not proof that no such input exists.`;
  return `A second AI (the breaker agent) attacked the Java and made it differ on ${n(b.broke)} of ${n(b.tried)} attack inputs, replays included; `
    + (b.fixed ? "the repair agent fixed it and the Java was checked again." : "the repair agent did not fix it within its limits.");
}

export function modelLines(run: Run): { role: string; models: string[] }[] {
  const calls: ModelCall[] = run.usage?.modelCalls ?? [];
  const roles = [...new Set(calls.map((c) => c.role))];
  return roles.map((role) => ({ role, models: [...new Set(calls.filter((c) => c.role === role).map((c) => c.model))] }));
}

export type CheckLine = { check: string; state: "done" | "not-run" | "flag" | "failed"; label: string; detail: string };

// The record's checks, kept apart: a check that did not happen says so and is never counted as a pass.
export function checkLines(run: Run): CheckLine[] {
  const after = run.after;
  const lines: CheckLine[] = [];
  const compared = !!after && after.total > 0;
  const patched = run.assurance === "certified-against-repaired-cobol";
  lines.push(compared
    ? { check: "Compiled and ran", state: "done", label: "yes", detail: patched ? "The original did not compile as written. A patched copy and the Java built and produced output." : "Both the original and the Java built and produced output." }
    : { check: "Compiled and ran", state: run.assurance === "compiled-unverified" ? "not-run" : "failed", label: run.assurance === "compiled-unverified" ? "compile only" : "no comparison", detail: "Nothing was compared on this record." });
  if (compared) {
    lines.push({
      check: "Agreement on tested inputs",
      state: after.failed === 0 && after.stdoutMatch ? "done" : "failed",
      label: `${n(after.passed)} of ${n(after.total)}`,
      detail: `Output records compared${after.stdoutMatch ? "; display output also matched" : "; display output DIFFERED"}. Generated records carry no deliberately bad data, and a flat text record gets placeholders.`,
    });
  }
  if (KNOWN_DIFFERENCE[run.id]) {
    lines.push({ check: "Known difference, found later", state: "failed", label: "yes", detail: `After this run, on ${KNOWN_DIFFERENCE[run.id]}` });
  }
  const b = run.breaker;
  if (!b || !(b.tried > 0)) {
    lines.push({ check: "Attack by the breaker", state: "not-run", label: "not run", detail: `No designed input was tried in this run: ${b?.skipped ?? (compared && after.failed === 0 && after.stdoutMatch ? "the breaker was off, or this program is not a single-file record program it can attack" : "it only attacks Java that passed")}. Not a pass.` });
  } else if (b.broke === 0) {
    lines.push({ check: "Attack by the breaker", state: "done", label: "survived", detail: `${n(b.tried)} attack inputs, none differed. A limited attack, not a proof.` });
  } else {
    lines.push({ check: "Attack by the breaker", state: b.fixed ? "done" : "failed", label: b.fixed ? "broken, then repaired" : "broken, not repaired", detail: `${n(b.broke)} of ${n(b.tried)} attack inputs differed, replays included.` });
  }
  const c = run.crosscheck;
  lines.push(!c
    ? { check: "Independent cross-check", state: "not-run", label: "not run", detail: "Opt-in; it did not run here. Not a pass." }
    : c.skipped
      ? { check: "Independent cross-check", state: "not-run", label: "skipped", detail: `It could not run (${clip(c.skipped, 120)}). Not a pass.` }
      : !c.casesValid
        ? { check: "Independent cross-check", state: "not-run", label: "no valid inputs", detail: "The model proposed nothing that fitted the layout, so nothing was tried. Not a pass." }
        : { check: "Independent cross-check", state: c.mismatches ? "failed" : "done", label: `${n(c.casesValid)} tried, ${n(c.mismatches ?? 0)} differed`, detail: "A second, open-weight model proposed inputs; each valid one was run through both programs." });
  const review = run.guard?.review;
  lines.push(!review
    ? { check: "Guard model review", state: "not-run", label: "not run", detail: "Policy only, or the run was not certified. Not a pass." }
    : review.verdict === "error"
      ? { check: "Guard model review", state: "not-run", label: "skipped", detail: `It did not complete (${clip(review.summary ?? "no reason recorded", 120)}). Not a pass; the comparison and the policy still ran.` }
      : review.verdict === "flag"
        ? { check: "Guard model review", state: "flag", label: "flag", detail: `It completed with findings to read: ${clip(review.summary ?? "no summary recorded", 160)}` }
        : { check: "Guard model review", state: review.verdict === "pass" ? "done" : "failed", label: review.verdict, detail: "One model review of the final Java. It can revoke a certification, never grant one." });
  return lines;
}

// What the comparison rests on, in the terms a person deciding on this Java needs.
export function comparedAgainst(run: Run): string[] {
  const after = run.after;
  const out = [run.assurance === "certified-against-repaired-cobol"
    ? "A PATCHED copy of the original, compiled with GnuCOBOL 3.2; not the original and not IBM Enterprise COBOL."
    : "The original compiled with GnuCOBOL 3.2 (IBM TRUNC(STD) and DISPLAY defaults); not IBM Enterprise COBOL."];
  if (after?.database) out.push("SQLite stands in for DB2, for a stated SQL subset.");
  if (after?.keyed) out.push("Berkeley DB stands in for VSAM, for a stated keyed-file subset.");
  for (const s of after?.standIns ?? []) out.push(`Diocle's own ${s.routine} routine stands in for IBM Language Environment.`);
  return out;
}

const CHECK_TEXT = { done: "done", "not-run": "not run", flag: "completed with findings", failed: "failed" } as const;

function WhatThisEstablished({ run }: { run: Run }) {
  if (run.status === "running" || run.status === "interrupted") return null;
  return (
    <div>
      <h3>What this run did and did not establish</h3>
      <div className="table-scroll">
        <table className="data-table plain-checks">
          <caption className="sr-only">Each check in this run and its state</caption>
          <thead><tr><th>Check</th><th>Result</th><th>What it means</th></tr></thead>
          <tbody>
            {checkLines(run).map((l) => (
              <tr key={l.check} data-state={l.state}>
                <td>{l.check}</td>
                <td title={CHECK_TEXT[l.state]}><strong>{l.label}</strong></td>
                <td>{l.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="plain-note"><strong>Compared against:</strong> {comparedAgainst(run).join(" ")}</p>
      <p className="plain-note"><strong>Not established:</strong> formal equivalence for every input, or behaviour on IBM Enterprise COBOL and z/OS. A person still reviews the code and accepts it on their own runtime.</p>
    </div>
  );
}

export function PlainEnglishCard({ run }: { run: Run }) {
  const claims = (run.behavior?.claims ?? []).filter((c) => c.status === "confirmed" && c.statement);
  const shown = claims.slice(0, MAX_CLAIMS);
  const breaker = breakerSentence(run);
  const models = modelLines(run);
  const cost = money(run.usage?.estimatedCostUsd);
  return (
    <section className="panel plain-card" aria-labelledby="plain-title">
      <div className="panel-heading">
        <div>
          <h2 id="plain-title"><MessageSquareText size={14} /> In plain English</h2>
          <p>Every line below comes from this run&apos;s record. Nothing is written about the program unless it was checked.</p>
        </div>
      </div>
      <div className="plain-body">
        {shown.length > 0 ? (
          <div>
            <h3>What this program does (each confirmed by running the original COBOL)</h3>
            <ul className="plain-claims">
              {shown.map((c) => <li key={c.id}>{clip(c.statement, MAX_CHARS)}</li>)}
            </ul>
            <p className="plain-note">
              Confirmed on the examples tried, not proven. A model wrote these sentences; GnuCOBOL ran the examples.
              {claims.length > shown.length ? ` Showing ${shown.length} of ${claims.length} confirmed claims; the Behaviour spec panel below has all of them.` : ""}
            </p>
          </div>
        ) : null}
        <div>
          <h3>Did the Java match?</h3>
          <p>{verdictSentence(run)}</p>
          {breaker && <p>{breaker}</p>}
          <p>
            {cost ? <>Estimated model cost for the whole run: <strong className="mono">{cost}</strong> (list prices). </> : "Cost not recorded. "}
            {models.length > 0 && (
              <>Models: {models.map((m, i) => (
                <span key={m.role}>{i ? "; " : ""}{ROLE_WORDS[m.role] ?? m.role}: <span className="mono">{m.models.join(", ")}</span>{m.models[0] ? ` (${hostOf(m.models[0])})` : ""}</span>
              ))}.</>
            )}
          </p>
        </div>
        <WhatThisEstablished run={run} />
      </div>
    </section>
  );
}
