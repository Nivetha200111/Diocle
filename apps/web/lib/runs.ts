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
  };
  model: string | null;
  javaDiff: string | null;
  efficiency: Efficiency;
  memory: RunMemory;
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
