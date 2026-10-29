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

export type Lesson = { pattern: string; cobol: string; java: string };

export type RunMemory = { enabled: boolean; used: number; learned: number; lessons: Lesson[] } | null;

export type RunListItem = {
  id: string;
  status?: "running" | "certified" | "not-certified";
  visitor?: boolean; // from a visitor's import: shown as reported, not re-verified here
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
};

export type FieldDiff = { field: string; original: string; converted: string };

export type Verification = {
  total: number;
  passed: number;
  failed: number;
  stdoutMatch: boolean;
  failingExamples: { inputId: string; inputSource?: string; diff: string; fieldDiffs?: FieldDiff[] }[];
};

export type RunEvent = {
  type: "agent-step" | "certification" | "budget" | "memory" | "stage" | "breaker";
  stage?: string;
  tried?: number;
  broke?: number;
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

export type Run = {
  id: string;
  visitor?: boolean;
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
};

// One logged model call. mode "hosted" is Muse Spark on the Meta Model API; "private" is Muse Spark Open on a partner host.
export type ModelCall = {
  role: "translator" | "repair" | "breaker" | string;
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
const PRICES: Record<string, [number, number, number]> = {
  "muse-spark-1.3-contributor": [0.10, 0.002, 0.20],
  "muse-spark-1.3": [1.25, 0.15, 4.25],
  "accounts/fireworks/models/muse-spark-open": [1.25, 0.15, 4.25],
};

export function callCostUsd(c: ModelCall): number | null {
  const p = PRICES[c.model];
  return p ? ((c.inputTokens - c.cachedInputTokens) * p[0] + c.cachedInputTokens * p[1] + c.outputTokens * p[2]) / 1e6 : null;
}

export const isPrivateModel = (model: string | null | undefined) => !!model && model.includes("muse-spark-open");

// contracts/run.schema.json breaker: a second agent designs inputs to break the certified Java.
export type Breaker = {
  rounds: number;
  tried: number;
  broke: number;
  repairCycles: number;
  fixed: boolean;
  counterexamples: { input: string; why: string; diff: string }[];
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

// A run left "running" by an engine restart: no model call and no heartbeat for hours.
export const isInterrupted = (r: Pick<RunListItem, "status" | "createdAt" | "efficiency">, now = Date.now()) =>
  r.status === "running" && r.efficiency.modelCalls === 0 && !!r.createdAt
  && now - Date.parse(r.createdAt) > 2 * 3600 * 1000;
