// Cost and speed statistics computed from the engine's run list. Pure functions so they can be tested without a browser.
import type { RunListItem } from "./runs";

export const median = (xs: number[]): number | null => {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};
export const mean = (xs: number[]): number | null => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);

// Only plain certified runs: a convert-anyway label (repaired COBOL, compiled-unverified, failed) is never counted.
export const isPlainCertified = (r: RunListItem) => r.certified && (r.assurance === undefined || r.assurance === "certified");

export type Stat = { value: number | null; n: number };
const stat = (xs: number[]): Stat => ({ value: median(xs), n: xs.length });

export type Scoreboard = {
  liveSampleRuns: number; // left out below: a button anyone can press must not move the statistics
  runsTotal: number;
  certifiedRuns: number;
  distinctPrograms: number;
  costMedian: Stat;
  costMean: Stat;
  costMax: number | null;
  timeMedianS: Stat;
  linesMedian: Stat;
  costPer1kMedian: Stat;
};

export function scoreboard(all: RunListItem[]): Scoreboard {
  const runs = all.filter((r) => !r.sampleRun);
  const ok = runs.filter(isPlainCertified);
  const finite = (xs: (number | null | undefined)[]) => xs.filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  const costs = finite(ok.map((r) => r.efficiency.estimatedCostUsd));
  return {
    liveSampleRuns: all.length - runs.length,
    runsTotal: runs.length,
    certifiedRuns: ok.length,
    distinctPrograms: new Set(ok.map((r) => r.program.toUpperCase())).size,
    costMedian: stat(costs),
    costMean: { value: mean(costs), n: costs.length },
    costMax: costs.length ? Math.max(...costs) : null,
    timeMedianS: stat(finite(ok.map((r) => r.efficiency.modelTimeMs)).filter((x) => x > 0).map((x) => x / 1000)),
    linesMedian: stat(finite(ok.map((r) => r.efficiency.cobolLines)).filter((x) => x > 0)),
    costPer1kMedian: stat(finite(ok.map((r) => r.efficiency.costPer1kLinesUsd))),
  };
}
