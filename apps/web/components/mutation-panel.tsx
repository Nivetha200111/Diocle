"use client";

import { useEffect, useState } from "react";
import { fetchMutation, runMutation, type MutationReport, type Run } from "@/lib/runs";

// "How strong is this verification?": seeded faults vs the inputs that certified the Java. Every string below is
// rendered as React text (escaped); nothing is injected as HTML. It is not a confidence score.
export function MutationPanel({ run }: { run: Run }) {
  const [report, setReport] = useState<MutationReport | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    if (run.certified && !run.visitor) fetchMutation(run.id).then((r) => live && setReport(r)).catch(() => {});
    return () => { live = false; };
  }, [run.id, run.certified, run.visitor]);
  if (!run.certified || run.visitor) return null;

  const disabledReason = busy ? "Running; this takes up to a few minutes." : "";
  const c = report?.counts;
  const detected = c ? c.killed + c.timeout : 0;
  const scored = c ? c.killed + c.timeout + c.survived : 0;
  const survivors = report?.mutants.filter((m) => m.outcome === "survived") ?? [];
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>How strong is this verification?</h2>
          <p>Small realistic mistakes are seeded into a copy of the Java (a flipped comparison, a changed rounding mode, a dropped truncation). Would the inputs that certified it have noticed? No model is involved.</p>
        </div>
      </div>
      <div className="reverify">
        <button className="button primary" disabled={busy} title={disabledReason || undefined} onClick={async () => {
          setBusy(true);
          setError("");
          try {
            // The POST is synchronous and can outlive a proxy timeout: on failure, look for the stored report a while.
            try {
              setReport(await runMutation(run.id));
            } catch (e) {
              let found: MutationReport | null = null;
              for (let i = 0; i < 12 && !found; i++) {
                await new Promise((r) => setTimeout(r, 5000));
                const latest = await fetchMutation(run.id).catch(() => null);
                if (latest && latest.runId === run.id && (!report || latest.seconds !== report.seconds)) found = latest;
              }
              if (found) setReport(found);
              else throw e;
            }
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}>{busy ? "Seeding faults…" : report ? "Run again" : "Test the verification"}</button>
        {disabledReason && <span className="mutation-note">{disabledReason}</span>}
        {error && <p className="reverify-result bad">{error}</p>}
      </div>
      {report && report.status !== "ok" && (
        <p className="mutation-note">Not run: {report.reason ?? report.status}</p>
      )}
      {report && c && report.status === "ok" && (
        <div className="mutation">
          <p className="reverify-result ok">
            Initial inputs ({report.inputs.initial.toLocaleString("en-US")}) detected {detected} of {scored} seeded faults
            {c.timeout > 0 && ` (of which ${c.timeout} timed out)`}
            {c.score !== null && ` (${Math.round(c.score * 100)}%)`}; extra inputs detected {report.augmented.extraKills} more
            ({report.augmented.extraInputs} extra inputs); {c.survived} survived the initial inputs
            ({report.augmented.stillSurviving ?? c.survived} still survive after the extra inputs);
            {" "}{c.notCompiled} did not compile; {c.equivalentSuspected} suspected equivalent
            {c.notRun > 0 && `; ${c.notRun} not run (time limit)`}
            {c.error > 0 && `; ${c.error} harness errors`}.
          </p>
          <p className="mutation-note">
            Inputs: {report.inputs.seedSource === "default"
              ? "this run recorded no certification seed, so a default seed was used (same kind of inputs, not the same ones)."
              : "generated from the run's certification seed."}
          </p>
          <p className="mutation-note">
            A survivor is a coverage question, not automatically a defect: no input exercised the difference, or the change is harmless. This is not a confidence score.
          </p>
          {survivors.length > 0 && (
            <ul className="mutation-list">
              {survivors.map((m) => (
                <li key={m.id}>
                  <code>{m.location.file}:{m.location.line}</code> {m.description}
                  {m.augmentedOutcome === "killed" && <> · caught by extra input <code>{m.augmentedKilledBy}</code></>}
                  {m.augmentedOutcome !== "killed" && <> · still survives</>}
                  <br />
                  <code>{m.original}</code> → <code>{m.mutated}</code>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
