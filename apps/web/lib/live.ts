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
  if ([400, 403, 409, 413, 429].includes(r.status)) {
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

// A visitor's own upload: the engine returns a key, and only that key can read the result. Kept for this tab only.
export function rememberViewKey(id: string, key: string) {
  try { sessionStorage.setItem(`diocle-view-${id}`, key); } catch { /* a blocked store only loses the result on reload */ }
  memoryKeys.set(id, key);
}
const memoryKeys = new Map<string, string>();
export function viewKey(id: string): string | null {
  if (memoryKeys.has(id)) return memoryKeys.get(id) ?? null;
  try { return sessionStorage.getItem(`diocle-view-${id}`); } catch { return null; }
}
export function viewHeaders(id: string): Record<string, string> {
  const key = viewKey(id);
  return key ? { "X-Diocle-View": key } : {};
}

export async function base64Of(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
}

// Phone photos are far over the limit: redraw at most 1600 px on a side as JPEG. Redrawing also drops the photo's metadata (GPS, device).
export async function shrinkImage(file: File, maxBytes: number): Promise<Blob> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  for (const quality of [0.88, 0.75, 0.6]) {
    const blob = await new Promise<Blob | null>((done) => canvas.toBlob(done, "image/jpeg", quality));
    if (blob && blob.size <= maxBytes) return blob;
  }
  throw new Error("The image is still too large after shrinking it.");
}

export async function startLiveUpload(image: Blob): Promise<string> {
  const r = await fetch(`${API_URL}/samples/live/upload`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ imageBase64: await base64Of(image) }),
  });
  if (!r.ok) throw new Error(await detail(r));
  const { id, key } = await r.json() as { id: string; key: string };
  rememberViewKey(id, key);
  return id;
}

export async function fetchJob(id: string): Promise<LiveJob> {
  const r = await fetch(`${API_URL}/samples/live/${encodeURIComponent(id)}`, { cache: "no-store", headers: viewHeaders(id), signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function fetchSamplesStatus(): Promise<SamplesStatus | null> {
  const r = await fetch(`${API_URL}/config`, { cache: "no-store", signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()).publicImports?.samples ?? null;
}
