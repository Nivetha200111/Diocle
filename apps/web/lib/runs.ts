// Types and fetchers for real converter runs served by services/api (contracts/run.schema.json).

export const API_URL = process.env.NEXT_PUBLIC_DIOCLE_API_URL ?? "http://localhost:8000";

export type Efficiency = {
  cobolLines: number;
  modelCalls: number;
  toolSteps: number;
  patchesApplied: number;
  cacheHitRate: number;
  totalTokens: number;
  modelTimeMs: number;
  estimatedCostUsd: number | null;
  costPer1kLinesUsd: number | null;
};

// contracts/run.schema.json `assurance` (convert-anyway mode). Absent on ordinary runs: read `certified`. Only "certified"
// is certified; the others are never counted in the front-page "N certified".
export type Assurance = "certified" | "certified-against-repaired-cobol" | "compiled-unverified" | "failed";

export const ASSURANCE_BADGE: Record<Assurance, { label: string; tone: string }> = {
  certified: { label: "CERTIFIED", tone: "green" },
  "certified-against-repaired-cobol": { label: "VERIFIED AGAINST REPAIRED COBOL", tone: "amber" },
  "compiled-unverified": { label: "COMPILED, NOT VERIFIED", tone: "amber" },
  failed: { label: "FAILED", tone: "red" },
};

export type CobolRepair = {
  method: "deterministic" | "model";
  outcome: "compiles" | "still-fails" | "rejected" | "cap-reached";
  diff: string;
  diagnostics: string[];
  fixes?: string[];
  changedLines: number;
  rounds?: number;
  modelCalls?: number;
  estimatedCostUsd?: number | null;
  patchedFile?: string;
};

export type Lesson = { pattern: string; cobol: string; java: string };

export type RunMemory = { enabled: boolean; used: number; learned: number; lessons: Lesson[] } | null;

// contracts/run.schema.json `sampleRun`: a live sample run. A real run, labelled, and left out of the scoreboard statistics.
export type SampleRun = { sample: "addfee"; live: true; job?: string };

export type RunListItem = {
  id: string;
  status?: "running" | "certified" | "not-certified" | "interrupted";
  visitor?: boolean; // from a visitor's import: shown as reported, not re-verified here
  sampleRun?: SampleRun; // started by the public "Convert a sample now" button (run schema v0.16)
  program: string;
  command: "repair" | "run";
  certified: boolean;
  createdAt: string | null;
  rounds: number;
  calls: number;
  estimatedCostUsd: number | null;
  model: string | null;
  efficiency: Efficiency;
  memory: RunMemory;
  assurance?: Assurance;
};

export type FieldDiff = { field: string; original: string; converted: string };

// verification-report v0.9 runs.database, passed through by GET /runs/{id} (run contract v0.15). Every field optional on read.
export type DatabaseTable = {
  name?: string;
  rowsSeeded?: number;
  rowsOriginal?: number;
  rowsConverted?: number;
  match?: boolean;
  firstMismatch?: { row?: number; column?: string; original?: string; converted?: string } | null;
  changedFromSeed?: { original?: boolean; converted?: boolean };
};
export type DatabaseComparison = {
  engine?: string;
  engineVersion?: string;
  subset?: string;
  seededFrom?: string;
  tables?: DatabaseTable[];
};

export type Verification = {
  total: number;
  passed: number;
  failed: number;
  stdoutMatch: boolean;
  database?: DatabaseComparison | null;
  failingExamples: { inputId: string; inputSource?: string; diff: string; fieldDiffs?: FieldDiff[] }[];
};

export type RunEvent = {
  type: "agent-step" | "certification" | "budget" | "memory" | "stage" | "breaker" | "crosscheck" | "guard" | "behavior";
  stage?: string;
  tried?: number;
  broke?: number;
  blocked?: boolean;
  round?: number;
  step?: number;
  tool?: string;
  rationale?: string;
  argsSummary?: Record<string, unknown>;
  resultSummary?: string;
  passed?: boolean;
  result?: string;
  message?: string;
};

import type { ReproducerSummary } from "./reproducer-view";

export type Run = {
  id: string;
  visitor?: boolean;
  sampleRun?: SampleRun;
  status?: "running" | "certified" | "not-certified" | "interrupted";
  error?: string | null;
  program: string;
  command: "repair" | "run";
  createdAt: string | null;
  certified: boolean;
  javaOrigin: string;
  rounds: { round: number; certified: boolean }[];
  events: RunEvent[];
  before: Verification | null;
  after: Verification | null;
  usage: {
    calls: number;
    inputTokens: number;
    cachedInputTokens: number;
    outputTokens: number;
    estimatedCostUsd: number | null;
    modelCalls?: ModelCall[];
  };
  model: string | null;
  javaDiff: string | null;
  efficiency: Efficiency;
  memory: RunMemory;
  breaker?: Breaker | null;
  reproducers?: ReproducerSummary[] | null;  // run v0.18: present when the run reduced counterexamples (--minimize)
  crosscheck?: Crosscheck | null;
  behavior?: Behavior | null;
  tiers?: Tiers | null;
  guard?: Guard | null;
  assurance?: Assurance;
  assuranceReason?: string | null;
  cobolRepair?: CobolRepair | null;
};

// One logged model call. mode "hosted" is Muse Spark on the Meta Model API; "private" is Muse Spark Open on a partner host.
export type ModelCall = {
  role: "translator" | "repair" | "breaker" | "crosscheck" | "document" | string;
  round: number;
  mode: string;
  model: string;
  inputTokens: number;
  cachedInputTokens: number;
  outputTokens: number;
  latencyMs: number;
};

// Mirrors PRICES in services/converter/diocle_converter/config.py (USD per million tokens: input, cached input,
// output), so the per-role split adds up to the run's own estimate.
export const PRICES: Record<string, [number, number, number]> = {
  "muse-spark-1.3-contributor": [0.10, 0.002, 0.20],
  "muse-spark-1.3": [1.25, 0.15, 4.25],
  "accounts/fireworks/models/muse-spark-open": [1.25, 0.15, 4.25],
  "meta-models/muse-spark-open-1026": [1.25, 0.15, 4.25],
  "muse-wonder-1.0": [4.0, 0.2, 20.0],  // per third-party coverage, unconfirmed on dev.meta.ai
};

export function callCostUsd(c: ModelCall): number | null {
  const p = PRICES[c.model];
  return p ? ((c.inputTokens - c.cachedInputTokens) * p[0] + c.cachedInputTokens * p[1] + c.outputTokens * p[2]) / 1e6 : null;
}

export const isPrivateModel = (model: string | null | undefined) => !!model && model.includes("muse-spark-open");

// Who served a model, from its ID: the same Meta weights reach us through different hosts.
export const hostOf = (model: string) =>
  model.startsWith("accounts/fireworks/") ? "Fireworks"
    : model.startsWith("meta-models/") ? "Baseten"
      : (model.startsWith("muse-spark-1") || model.startsWith("muse-wonder")) ? "Meta Model API" : "partner host";

// contracts/run.schema.json $defs.guard: the guard agent's policy findings and its model review.
export type GuardFinding = {
  severity: "block" | "flag"; category: string; file: string | null; line: number | null; explanation: string;
};
export type Guard = {
  blocked: boolean;
  stopped?: number;
  policy: GuardFinding[];
  sourceFlags?: GuardFinding[];
  review: { model: string; verdict: "pass" | "flag" | "block" | "error"; summary: string; findings: GuardFinding[] } | null;
};

// contracts/run.schema.json breaker: a second agent designs inputs to break the certified Java.
export type Breaker = {
  rounds: number;
  tried: number;
  broke: number;
  repairCycles: number;
  fixed: boolean;
  counterexamples: { input: string; why: string; diff: string }[];
};

// contracts/run.schema.json crosscheck: Muse Spark Open independently looks for inputs where the Java differs. Its opinion
// certifies nothing; only cases that really differ on GnuCOBOL vs Java count.
export type Crosscheck = {
  model?: string;
  casesProposed?: number;
  casesValid?: number;
  mismatches?: number;
  repairCycles?: number;
  fixed?: boolean;
  suspected?: { field: string; concern: string }[];
  counterexamples?: { input: string; why: string; diff: string }[];
  skipped?: string;
};

// contracts/behavior-claims.schema.json v0.1 (run.behavior): verified documentation. A model wrote the claims; GnuCOBOL ran
// every example on the original COBOL and decided. Wording: "confirmed on the examples tried", never "proven".
export type FieldValues = Record<string, string>;
export type ClaimStatus = "confirmed" | "refuted" | "unchecked";
export type ClaimExample = {
  id: string;
  inputs: FieldValues[];
  expected: { records?: FieldValues[]; outputRecordCount?: number; stdoutContains?: string; returnCode?: number };
  status: "matched" | "differed" | "unchecked";
  actual?: { records?: FieldValues[]; outputRecordCount?: number; stdout?: string; returnCode?: number | null } | null;
  mismatches?: { what: string; expected: string; actual: string }[];
  reason?: string;
};
export type BehaviorClaim = { id: string; statement: string; status: ClaimStatus; examples: ClaimExample[]; reason?: string };
export type Behavior = {
  version?: string;
  program: string;
  model: string;
  checkedWith: string;
  summary: { claims: number; confirmed: number; refuted: number; unchecked: number; examplesRun: number };
  claims: BehaviorClaim[];
  usage?: { calls?: number; inputTokens?: number; outputTokens?: number; estimatedCostUsd?: number | null };
  skipped?: string;
};

// contracts/run.schema.json tiers: the repair agent moves up one model tier after each failed certification round.
export type Tiers = {
  enabled: boolean;
  configured: string[];
  escalations: { round: number; tier: number; model: string }[];
  breakerModel?: string | null;
  escalatedCalls?: number;
  escalatedUsd?: number;
  capCalls?: number;
  capUsd?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export const fetchRuns = () => getJson<RunListItem[]>("/runs");
export const fetchRun = (id: string) => getJson<Run>(`/runs/${encodeURIComponent(id)}`);

export type Reverify = {
  runId: string; seed: number; passed: number; total: number; failed: number;
  stdoutMatch: boolean; exitCodeMatch: boolean; allMatch: boolean; firstMismatch: string | null; seconds: number;
};

export async function reverifyRun(id: string): Promise<Reverify> {
  const response = await fetch(`${API_URL}/runs/${encodeURIComponent(id)}/reverify`, { method: "POST" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data as Reverify;
}

// contracts/run.schema.json $defs.source: the original COBOL next to the run's Java.
export type SourceFile = { path: string; text: string; truncated?: boolean };
export type RunSource = { runId: string; program: string; cobol: SourceFile[]; java: SourceFile[] };

export const fetchRunSource = (id: string) => getJson<RunSource>(`/runs/${encodeURIComponent(id)}/source`);

// contracts/sql-schema.schema.json: the copybooks as SQL tables, with the SQLite round trip that proves they hold
// every byte. Deterministic, no model.
export type SqlSchema = {
  runId: string; ddl: string;
  tables: { table: string; record: string; roundTrip: { records: number; identical: number; sources: string[] } }[];
  summary: { tables: number; records: number; identical: number; passed: boolean };
};

// contracts/minimal-reproducer.schema.json: read-only, produced without a model by services/verifier minimize.
export type RunReproducers = { runId: string; reproducers: unknown[] };
export type RegressionDownload = { runId: string; case: string; files: { name: string; base64: string }[]; replay: string };
export const fetchRunReproducers = (id: string) => getJson<RunReproducers>(`/runs/${encodeURIComponent(id)}/reproducers`);
export const fetchRegressionCase = (id: string, caseId: string) =>
  getJson<RegressionDownload>(`/runs/${encodeURIComponent(id)}/reproducers/${encodeURIComponent(caseId)}/regression`);

export const fetchRunSchema = (id: string) => getJson<SqlSchema>(`/runs/${encodeURIComponent(id)}/schema`);

const count = (n: number) => n.toLocaleString("en-US");

export const schemaFile = (s: SqlSchema): SourceFile => ({
  path: "schema.sql",
  text: "-- The copybooks as SQL tables, generated without a model.\n"
    + `-- Round trip: ${s.summary.passed ? "all " : ""}${count(s.summary.identical)} of ${count(s.summary.records)} generated `
    + "records (PIC boundaries and seeded random values) fit\n-- these column types, went into an SQLite copy of the "
    + `tables and came back byte for byte${s.summary.passed ? "." : "; the others did not."}\n\n${s.ddl}`,
});

// A run cut off by an engine restart. Newer engines say so ("interrupted"); for older ones, a run still "running"
// with no model call a full day after its (timezone-less) start time was certainly cut off.
export const isInterrupted = (r: Pick<RunListItem, "status" | "createdAt" | "efficiency">, now = Date.now()) =>
  r.status === "interrupted" || (r.status === "running" && r.efficiency.modelCalls === 0 && !!r.createdAt
    && now - Date.parse(r.createdAt) > 24 * 3600 * 1000);

// contracts/mutation-report.schema.json v0.1: seeded faults vs the inputs that certified this Java. Deterministic, no model.
export type Mutant = {
  id: string; operator: string; location: { file: string; line: number }; original?: string; mutated?: string;
  description: string; outcome: "killed" | "survived" | "not-compiled" | "equivalent-suspected" | "timeout" | "error";
  killedBy?: string | null; augmentedOutcome?: "killed" | "survived"; augmentedKilledBy?: string | null; note?: string;
};
export type MutationReport = {
  version: string; runId?: string | null; program?: string | null; status: "ok" | "unsupported" | "baseline-failed"; reason?: string | null;
  seed: number; inputs: { initial: number; seed?: number; seedSource?: "certification" | "default" };
  counts: { generated: number; run: number; killed: number; survived: number; notCompiled: number; equivalentSuspected: number;
            timeout: number; error: number; notRun: number; score: number | null };
  mutants: Mutant[];
  augmented: { extraInputs: number; survivorsRerun: number; extraKills: number; stillSurviving?: number };
  seconds?: number; notes: string[];
};

export const fetchMutation = async (id: string): Promise<MutationReport | null> => {
  const response = await fetch(`${API_URL}/runs/${encodeURIComponent(id)}/mutation`, { cache: "no-store" });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<MutationReport>;
};

export async function runMutation(id: string): Promise<MutationReport> {
  const response = await fetch(`${API_URL}/runs/${encodeURIComponent(id)}/mutation`, { method: "POST" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data as MutationReport;
}
