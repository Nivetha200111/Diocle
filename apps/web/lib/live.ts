// The two public "try it live" buttons (contracts/live-sample.schema.json). The request is a name from a fixed list.
import { API_URL } from "./runs";
import type { SamplesStatus } from "./config";

export type LiveSample = "addfee" | "loyalty-waiver-printout";

export type JobEvent = { at: string; message: string };
export type PrintoutResult = {
  status: "verified-identical" | "differs" | "compiled-unchecked" | "compile-failed" | "refused" | "no-transcription";
  reason: string | null;
  model: string | null;
  program: string | null;
  source: string | null;
  usage: { calls: number; inputTokens: number; outputTokens: number; estimatedCostUsd: number | null };
  attempts: { n: number; compileOk: boolean; errors?: string }[];
  differential: null | {
    ran: boolean; inputs: number; matched: number; mismatched: number; stdoutMatch?: boolean; exitCodeMatch?: boolean;
    reason?: string; ranIn?: "sandbox";
  };
};
export type LiveJob = {
  version: "0.1";
  id: string;
  sample: LiveSample;
  status: "running" | "done" | "failed";
  stage: string;
  startedAt: string;
  finishedAt: string | null;
  error: string | null;
  maxUsd: number;
  events: JobEvent[];
  runId: string | null;
  printout: PrintoutResult | null;
};

export const printoutImageUrl = `${API_URL}/samples/printout-image`;

async function detail(r: Response): Promise<string> {
  // Only the engine's own refusal sentences (429/409/403) are shown; anything else is a generic line.
  if ([403, 409, 429].includes(r.status)) {
    const body = await r.json().catch(() => ({}));
    if (typeof body.detail === "string") return body.detail.slice(0, 300);
  }
  return `The engine refused the request (HTTP ${r.status}).`;
}

export async function startLive(sample: LiveSample): Promise<string> {
  const r = await fetch(`${API_URL}/samples/live`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return (await r.json()).id as string;
}

export async function fetchJob(id: string): Promise<LiveJob> {
  const r = await fetch(`${API_URL}/samples/live/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function fetchSamplesStatus(): Promise<SamplesStatus | null> {
  const r = await fetch(`${API_URL}/config`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()).publicImports?.samples ?? null;
}
