// Smallest-reproducer card (contracts/minimal-reproducer.schema.json). Everything is read defensively and capped: a partial,
// older or hostile record must render (or render nothing), never crash the run page. Strings are shown as React text (escaped).

export type ReproducerSummary = { id: string; status: string; recordsBefore?: number; recordsAfter?: number; oracleRuns?: number; afterRepairPassed?: boolean | null };

export type FieldRow = { name: string; view: string; where: string; value: string; needed: boolean };
export type ReproducerView = {
  id: string;
  status: string;
  reason: string;
  program: string;
  source: string;
  headline: string;
  stats: string;
  stopped: string;
  discrepancy: string;
  inputText: string[];
  needed: FieldRow[];
  neutralCount: number;
  neutral: FieldRow[];
  original: string[];
  translated: string[];
  firstDifference: string;
  explanation: { text: string; label: string; source: string } | null;
  regression: { dir: string; files: string[]; replay: string; afterRepair: string } | null;
};

export const cap = (v: unknown, n = 200): string => {
  const s = typeof v === "string" ? v : typeof v === "number" || typeof v === "boolean" ? String(v) : "";
  return s.length > n ? s.slice(0, n) + "…" : s;
};
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const n = (v: number) => v.toLocaleString("en-US");
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const SOURCES: Record<string, string> = { breaker: "the breaker's input", "held-out": "a held-out certification input", "initial-test": "a starting-test input", manual: "an input chosen by hand" };

export function reproducerView(raw: unknown): ReproducerView | null {
  const r = obj(raw);
  if (typeof r.id !== "string" || typeof r.status !== "string") return null;
  const red = obj(r.reduction);
  const before = num(red.recordsBefore), after = num(red.recordsAfter);
  const minimized = r.status === "minimized";
  const rec = obj(arr(obj(arr(r.inputs)[0]).records)[0]);
  const allRecords = arr(obj(arr(r.inputs)[0]).records).slice(0, 5).map((x) => obj(x));
  const rows: FieldRow[] = arr(rec.fields).slice(0, 60).map((x) => {
    const f = obj(x);
    return { name: cap(f.name, 60), view: cap(f.view, 60), where: `byte ${num(f.offset)}, ${num(f.length)} long`, value: cap(f.value, 80), needed: f.role === "needed" };
  });
  const out = obj(r.output);
  const lines = (side: unknown) => arr(obj(side).records).slice(0, 5).map((x) => cap(x, 200));
  const d = obj(out.firstDifference);
  const ex = obj(r.explanation);
  const rg = obj(r.regression);
  const after2 = obj(rg.afterRepair);
  const stoppedBy = cap(red.stoppedBy, 20);
  return {
    id: cap(r.id, 80),
    status: cap(r.status, 30),
    reason: cap(r.reason, 300),
    program: cap(r.program, 40),
    source: SOURCES[cap(r.source, 20)] ?? "",
    headline: minimized
      ? `${n(before)} record${before === 1 ? "" : "s"} → ${n(after)} record${after === 1 ? "" : "s"} (${n(num(red.bytesBefore))} → ${n(num(red.bytesAfter))} bytes)`
      : "",
    stats: `${n(num(red.oracleRuns))} of at most ${n(num(red.maxOracleRuns))} differential runs · ${num(red.wallClockSeconds)} s`,
    stopped: stoppedBy === "complete" ? (red.recordMinimal ? "complete: no single record can be removed without losing the difference" : "complete") : stoppedBy ? `stopped by the ${stoppedBy}: smaller than the original, not known to be minimal` : "",
    discrepancy: cap(obj(r.discrepancy).summary, 200),
    inputText: allRecords.map((x) => cap(x.text, 200)),
    needed: rows.filter((x) => x.needed),
    neutralCount: rows.filter((x) => !x.needed).length,
    neutral: rows.filter((x) => !x.needed),
    original: lines(out.original),
    translated: lines(out.translated),
    firstDifference: d.record === undefined ? "" : `output record ${num(d.record)}${d.field ? `, field ${cap(d.field, 60)}` : ""}, byte ${num(d.offset)}`,
    explanation: typeof ex.text === "string" ? { text: cap(ex.text, 600), label: "explanation, not proof", source: cap(ex.source, 30) } : null,
    regression: typeof rg.dir === "string"
      ? {
          dir: cap(rg.dir, 120), files: arr(rg.files).slice(0, 6).map((f) => cap(f, 160)), replay: cap(rg.replay, 240),
          afterRepair: after2.passed === true ? "passes on the repaired Java" : after2.passed === false ? "FAILS on the repaired Java" : "not replayed yet",
        }
      : null,
  };
}
