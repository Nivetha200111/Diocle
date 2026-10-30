"use client";

// Cost and speed scoreboard, computed live from the engine's runs, with a human-review comparison that is an
// ASSUMPTION the visitor edits (component state only; nothing is stored).
import { useState } from "react";
import type { RunListItem } from "@/lib/runs";
import { humanCost, scoreboard } from "@/lib/scoreboard";

const usd = (n: number | null) => (n === null ? "n/a" : `$${n < 1 ? n.toFixed(4) : n.toFixed(2)}`);
const secs = (s: number | null) => (s === null ? "n/a" : s >= 120 ? `${(s / 60).toFixed(1)} min` : `${Math.round(s)} s`);

function Num({ id, label, value, onChange, step }: { id: string; label: string; value: string; onChange: (v: string) => void; step: string }) {
  return (
    <label htmlFor={id} className="sb-field">
      <span>{label}</span>
      <input id={id} type="number" inputMode="decimal" min="0" step={step} value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

export default function ScoreboardPanel({ runs, failed }: { runs: RunListItem[] | null; failed: boolean }) {
  const [hours, setHours] = useState("4");
  const [rate, setRate] = useState("75");
  if (failed) {
    return (
      <section className="panel" aria-labelledby="sb-h" role="alert">
        <div className="panel-heading"><div><h2 id="sb-h">Cost and speed scoreboard</h2>
          <p>The engine could not be reached, so there is nothing to compute. No numbers are shown in their place.</p></div></div>
      </section>
    );
  }
  if (runs === null) return <section className="panel" aria-busy="true"><div className="panel-heading"><div><h2>Cost and speed scoreboard</h2><p>Loading the engine&apos;s runs.</p></div></div></section>;
  const sb = scoreboard(runs);
  if (!sb.certifiedRuns) {
    return (
      <section className="panel" aria-labelledby="sb-h">
        <div className="panel-heading"><div><h2 id="sb-h">Cost and speed scoreboard</h2>
          <p>The engine holds {runs.length} runs and none is plain certified yet, so there is no cost per certified program to show.</p></div></div>
      </section>
    );
  }
  const human = humanCost(parseFloat(hours), parseFloat(rate));
  const per = sb.costMedian.value;
  const ratio = human !== null && per !== null && per > 0 ? human / per : null;
  const cell = (label: string, value: string, n: number, what = "runs") => (
    <div><dt>{label} <small className="sb-n">({n} {what})</small></dt><dd className="mono">{value}</dd></div>
  );
  return (
    <section className="panel" aria-labelledby="sb-h">
      <div className="panel-heading"><div>
        <h2 id="sb-h">Cost and speed scoreboard</h2>
        <p>Computed from the engine&apos;s runs just now. Only plain certified runs count; costs are estimates from list prices.</p>
      </div></div>
      <dl className="eff-grid home-evidence sb-grid">
        {cell("Certified runs", String(sb.certifiedRuns), sb.runsTotal, "runs kept")}
        {cell("Distinct programs", String(sb.distinctPrograms), sb.certifiedRuns)}
        {cell("Median cost per certified program", usd(sb.costMedian.value), sb.costMedian.n)}
        {cell("Mean cost per certified program", usd(sb.costMean.value), sb.costMean.n)}
        {cell("Median model time", secs(sb.timeMedianS.value), sb.timeMedianS.n)}
        {cell("Median COBOL lines", sb.linesMedian.value === null ? "n/a" : String(Math.round(sb.linesMedian.value)), sb.linesMedian.n)}
        {cell("Median cost per 1,000 lines", usd(sb.costPer1kMedian.value), sb.costPer1kMedian.n)}
      </dl>
      <p className="home-pr">
        {sb.costMean.value !== null && sb.costMedian.value !== null && sb.costMean.value > sb.costMedian.value
          ? "The mean is above the median: a few certified runs cost much more than the typical one (for example runs that used the dearer escalation tiers or a breaker on a bigger model)"
          : "The mean and the median are close here"}
        {" "}(the dearest certified run here is {usd(sb.costMax)}). Several runs can be the same program; that is why runs, not programs, are counted.
      </p>
      <div className="sb-human">
        <h3>Against a human reviewer</h3>
        <p className="sb-assume"><strong>Assumption, not a measurement: edit it.</strong> Nobody timed an engineer on these programs.</p>
        <div className="sb-inputs">
          <Num id="sb-hours" label="Hours of an engineer to convert and review one program like this" value={hours} onChange={setHours} step="0.5" />
          <Num id="sb-rate" label="Loaded hourly rate (USD)" value={rate} onChange={setRate} step="5" />
        </div>
        <p className="sb-result" aria-live="polite">
          {human === null || per === null
            ? "Enter a positive number of hours and a positive hourly rate."
            : `Assumed human cost ${usd(human)} per program, against a median model cost of ${usd(per)}: ${ratio !== null ? `about ${ratio >= 10 ? Math.round(ratio).toLocaleString("en-US") : ratio.toFixed(1)} times as much` : "no ratio (the model cost is zero)"}.`}
        </p>
        <p className="sb-not">
          Not counted: an engineer reading the certificate and the diff, the verifier&apos;s own compute (GnuCOBOL and Java runs), hosting,
          and the time to set the programs up. Runs that failed or were interrupted are not in these figures, but they cost money too and are
          counted on this page under &quot;Everything this engine has kept&quot;. Nothing you type here is saved or sent.
        </p>
      </div>
    </section>
  );
}
