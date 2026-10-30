"use client";

// Cost and speed scoreboard, computed live from the engine's runs. Raw model spend only; no human-cost comparison.
import type { RunListItem } from "@/lib/runs";
import { scoreboard } from "@/lib/scoreboard";

const usd = (n: number | null) => (n === null ? "n/a" : `$${n < 1 ? n.toFixed(4) : n.toFixed(2)}`);
const secs = (s: number | null) => (s === null ? "n/a" : s >= 120 ? `${(s / 60).toFixed(1)} min` : `${Math.round(s)} s`);

export default function ScoreboardPanel({ runs, failed }: { runs: RunListItem[] | null; failed: boolean }) {
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
  const cell = (label: string, value: string, n: number, what = "runs") => (
    <div><dt>{label} <small className="sb-n">({n} {what})</small></dt><dd className="mono">{value}</dd></div>
  );
  return (
    <section className="panel" aria-labelledby="sb-h">
      <div className="panel-heading"><div>
        <h2 id="sb-h">Cost and speed scoreboard</h2>
        <p>Computed from the engine&apos;s runs just now. Only plain certified runs count; costs are estimates from list prices.{sb.liveSampleRuns > 0 && ` ${sb.liveSampleRuns} live sample run${sb.liveSampleRuns === 1 ? "" : "s"} from the public \"Convert a sample now\" button ${sb.liveSampleRuns === 1 ? "is" : "are"} left out so a button anyone can press cannot move these numbers.`}</p>
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
      <p className="sb-not">
        These are raw model spend at list prices. They exclude the verifier&apos;s own compute (GnuCOBOL and Java runs), hosting, setup time
        and the human review of the equivalence report and the diff. No comparison with human cost is made: nobody timed an engineer on these
        programs. Runs that failed or were interrupted are not in these figures, but they cost money too and are counted on this page under
        &quot;Everything this engine has kept&quot;.
      </p>
    </section>
  );
}
