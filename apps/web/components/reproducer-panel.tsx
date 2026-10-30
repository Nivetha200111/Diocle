"use client";

import { useEffect, useState } from "react";
import { Microscope } from "lucide-react";
import { fetchRegressionCase, fetchRunReproducers } from "@/lib/runs";
import { reproducerView, type ReproducerView } from "@/lib/reproducer-view";
import { Badge } from "./ui";

// "Smallest reproducer": the failing input after deterministic reduction (no model), with the fields that matter named, what
// each side wrote, and the saved regression case. The suspected cause, when shown, is an opinion and says so.
// All strings go through React text nodes (escaped); the view model caps their length.

const visible = (s: string) => `"${s.replace(/ /g, "␣")}"`;

function download(runId: string, id: string, setNote: (s: string) => void) {
  fetchRegressionCase(runId, id)
    .then((c) => {
      const blob = new Blob([JSON.stringify(c, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `regression-${id}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
      setNote("");
    })
    .catch(() => setNote("The regression case is not available from this engine."));
}

function Card({ runId, v }: { runId: string; v: ReproducerView }) {
  const [note, setNote] = useState("");
  const minimized = v.status === "minimized";
  return (
    <div className="repro-card">
      <h3 className="mono">{v.id}</h3>
      {!minimized && <p>{v.status === "not-reproduced" ? "Not reproduced: " : "Not reduced: "}{v.reason}</p>}
      {minimized && (
        <>
          <p className="repro-headline">
            <strong>{v.headline}</strong> · {v.stats}
            {v.source ? <> · starting from {v.source}</> : null}
          </p>
          <p className="repro-small">{v.stopped}</p>
          {v.mode && <p className="repro-small">Same discrepancy meant {v.mode}.</p>}
          {v.origin && <p className="repro-origin"><Badge tone="amber">origin</Badge> {v.origin}</p>}
          <p><strong>What differs:</strong> {v.discrepancy}{v.firstDifference ? <> · first difference at {v.firstDifference}</> : null}</p>

          <h4>Minimized input</h4>
          {v.inputText.map((t, i) => <pre key={i} className="repro-pre">{visible(t)}</pre>)}
          <div className="table-scroll">
            <table className="data-table">
              <caption className="sr-only">Input fields the difference needs</caption>
              <thead><tr><th scope="col">Field</th><th scope="col">Position</th><th scope="col">Value</th></tr></thead>
              <tbody>
                {v.needed.map((f, i) => (
                  <tr key={i}>
                    <th scope="row" className="mono">{f.name}{f.view ? <span className="repro-small"> (view of {f.view})</span> : null}</th>
                    <td>{f.where}</td>
                    <td className="mono">{visible(f.value)}</td>
                  </tr>
                ))}
                {v.needed.length === 0 && <tr><td colSpan={3}>No single field is needed on its own (or the layout is not described field by field).</td></tr>}
              </tbody>
            </table>
          </div>
          {v.neutralCount > 0 && (
            <details>
              <summary>{v.neutralCount} other field(s) were set to zero or spaces and the difference stayed</summary>
              <p className="mono repro-small">{v.neutral.map((f) => f.name).join(", ")}</p>
            </details>
          )}

          <h4>Original (GnuCOBOL) against translated (Java)</h4>
          <div className="repro-sides">
            <div><Badge tone="green">COBOL wrote</Badge>{v.original.map((t, i) => <pre key={i} className="repro-pre">{visible(t)}</pre>)}</div>
            <div><Badge tone="amber">Java wrote</Badge>{v.translated.map((t, i) => <pre key={i} className="repro-pre">{visible(t)}</pre>)}</div>
          </div>

          {v.explanation && (
            <p className="repro-explain">
              <Badge tone="amber">{v.explanation.label}</Badge> The {v.explanation.source}&apos;s guess at the cause: {v.explanation.text}
            </p>
          )}

          {v.regression && (
            <div className="repro-regress">
              <h4>Regression test</h4>
              <p>
                A saved case: this input plus the bytes GnuCOBOL wrote for it. The verifier replays it against any Java; it fails on
                a Java with this defect and passes on a correct one. Status: <strong>{v.regression.afterRepair}</strong>.
              </p>
              <p className="mono repro-small">{v.regression.replay}</p>
              <p className="repro-small">Files: {v.regression.files.join(", ")}</p>
              <button type="button" className="text-button" onClick={() => download(runId, v.id, setNote)}>Download the regression case</button>
              {note && <p role="status">{note}</p>}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function ReproducerPanel({ runId, expected }: { runId: string; expected: boolean }) {
  const [views, setViews] = useState<ReproducerView[] | null>(null);
  useEffect(() => {
    if (!expected) return;
    let live = true;
    fetchRunReproducers(runId)
      .then((r) => live && setViews((Array.isArray(r.reproducers) ? r.reproducers : []).map(reproducerView).filter((x): x is ReproducerView => x !== null)))
      .catch(() => live && setViews([]));  // older engines have no such route: show nothing
    return () => { live = false; };
  }, [runId, expected]);
  if (!expected || !views || views.length === 0) return null;
  return (
    <section className="panel repro-panel" aria-labelledby="repro-heading">
      <div className="panel-heading">
        <div>
          <h2 id="repro-heading"><Microscope size={14} /> Smallest reproducer</h2>
          <p>
            Where the Java differed from the COBOL, the failing input was cut down automatically (no model, no guessing: each
            smaller input is run through both programs and compared byte for byte) to the smallest one that still differs.
          </p>
        </div>
      </div>
      {views.map((v) => <Card key={v.id} runId={runId} v={v} />)}
    </section>
  );
}
