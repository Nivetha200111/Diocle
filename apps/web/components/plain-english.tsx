"use client";

import { MessageSquareText } from "lucide-react";
import { hostOf, type ModelCall, type Run } from "@/lib/runs";

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
    return `The original COBOL did not compile, so it was patched. The Java matched the PATCHED COBOL${counts ? ` on ${counts} held-out inputs` : ""}; a person must confirm the patch keeps the original's meaning.`;
  }
  if (run.certified && counts) {
    const first = run.before && run.before.failed > 0
      ? ` Its first Java failed ${n(run.before.failed)} of ${n(run.before.total)} starting tests and was repaired.` : "";
    return `The Java matched the original COBOL on ${counts} held-out inputs (inputs the repair agent never saw), field by field and byte for byte${after?.stdoutMatch === false ? ", except printed output" : ""}${reported}.${first} "Certified" means on the inputs tried, not proven for every input.`;
  }
  if (run.certified) return `Certified${reported}, but this record has no held-out input counts to quote.`;
  if (counts) return `Not certified: the Java matched the original on only ${counts} held-out inputs.`;
  const why = run.error ? ` The run record says: ${clip(run.error.replace(/\s+/g, " "), 160)}` : "";
  return `Not certified: the run ended before a comparison could be made.${why}`;
}

export function breakerSentence(run: Run): string | null {
  const b = run.breaker;
  if (!b || !(b.tried > 0)) return null;
  if (b.broke === 0) return `A second AI (the breaker agent) designed ${n(b.tried)} inputs to break the Java; none did.`;
  return `A second AI (the breaker agent) attacked the Java and broke it with ${n(b.broke)} of ${n(b.tried)} inputs it designed; `
    + (b.fixed ? "the repair agent fixed it and the Java was checked again." : "the repair agent did not fix it within its limits.");
}

export function modelLines(run: Run): { role: string; models: string[] }[] {
  const calls: ModelCall[] = run.usage?.modelCalls ?? [];
  const roles = [...new Set(calls.map((c) => c.role))];
  return roles.map((role) => ({ role, models: [...new Set(calls.filter((c) => c.role === role).map((c) => c.model))] }));
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
        ) : (
          <div>
            <h3>What this program does</h3>
            <p className="plain-none">No plain-English summary was generated for this run.</p>
            <p className="plain-note">
              Run verified documentation to get one: <code>python -m diocle_converter run SAMPLE --document</code>
              {" "}(see <a href="https://github.com/Nivetha200111/Diocle#verified-documentation" target="_blank" rel="noreferrer">README: Verified documentation</a>).
              It is optional and not on every run.
            </p>
          </div>
        )}
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
      </div>
    </section>
  );
}
