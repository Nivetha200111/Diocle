// "Ask the original program" (contracts/voice-question.schema.json). The public request is two names from fixed lists.
import { API_URL } from "./runs";

export type AskSample = "interest-accrual" | "loyalty-waiver";
export type AskClip = "fee-overdrawn" | "waiver-tenure";

export type AskClipInfo = { clip: AskClip; sample: AskSample; question: string; seconds: number };
export type AsksStatus = {
  enabled: boolean; available: boolean; reason: string | null; maxUsd: number; perVisitorPerDay: number; perDay: number;
  usedToday: number; visitorLeft: number; uploadsAllowed: boolean; clips: AskClipInfo[];
};

export type Transcript = {
  text: string; model: string | null; audioSeconds: number; costUsd: number | null; priceConfirmed: boolean;
  source: "bundled-clip" | "uploaded-clip" | "typed-text";
};
export type ExampleResult = {
  id: string; inputs: Record<string, string>[]; status: "matched" | "differed" | "unchecked"; reason?: string;
  expected: { records?: Record<string, string>[] };
  actual?: { records?: Record<string, string>[]; returnCode?: number | null };
  mismatches?: { what: string; expected: string; actual: string }[];
};
export type ClaimResult = { id: string; statement: string; status: "confirmed" | "refuted" | "unchecked"; examples: ExampleResult[]; reason?: string };
export type AskResult = {
  version: "0.1"; sample: AskSample; clip: AskClip | null; transcript: Transcript;
  behavior: { model: string; checkedWith: string; claims: ClaimResult[]; skipped?: string };
  answer: { text: string; basis: "confirmed-claims" | "none-confirmed"; confirmedClaimIds: string[]; refutedClaimIds: string[] };
  verdict: { claims: number; confirmed: number; refuted: number; unchecked: number };
  costs: { transcribeUsd: number | null; claimsUsd: number | null; totalUsd: number | null };
  caps: { maxUsd: number };
  decidedBy: "GnuCOBOL"; stopped: string | null;
};
export type AskJob = {
  version: "0.1"; id: string; sample: AskSample; clip: AskClip | null; status: "running" | "done" | "failed";
  stage: "starting" | "transcribing" | "claims" | "checking" | "answering" | "done" | "failed";
  startedAt: string; finishedAt: string | null; error: string | null; events: { at: string; message: string }[];
  result: AskResult | null; partial: { transcript?: Transcript; proposed?: string[] } | null;
};

export const clipUrl = (clip: AskClip) => `${API_URL}/asks/clips/${clip}`;

async function detail(r: Response): Promise<string> {
  // Only the engine's own refusal sentences are shown; anything else is a generic line.
  if ([400, 403, 409, 413, 429].includes(r.status)) {
    const body = await r.json().catch(() => ({}));
    if (typeof body.detail === "string") return body.detail.slice(0, 300);
  }
  return `The engine refused the request (HTTP ${r.status}).`;
}

export async function startAsk(sample: AskSample, clip: AskClip): Promise<string> {
  const r = await fetch(`${API_URL}/asks`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample, clip }) });
  if (!r.ok) throw new Error(await detail(r));
  return (await r.json()).id as string;
}

// Local engine only (the engine refuses this from anyone else): the recorded clip as base64 WAV.
export async function startAskUpload(sample: AskSample, wav: Blob): Promise<string> {
  const bytes = new Uint8Array(await wav.arrayBuffer());
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  const r = await fetch(`${API_URL}/asks/upload`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sample, audioBase64: btoa(bin) }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return (await r.json()).id as string;
}

export async function fetchAsk(id: string): Promise<AskJob> {
  const r = await fetch(`${API_URL}/asks/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

export async function fetchAsksStatus(): Promise<AsksStatus | null> {
  const r = await fetch(`${API_URL}/config`, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()).publicImports?.asks ?? null;
}

// Microphone: 16 kHz mono 16-bit PCM WAV, which is the only thing the engine accepts.
export function encodeWav(samples: Float32Array, rate: number): Blob {
  const target = 16000;
  let data = samples;
  if (rate !== target) {  // the browser ignored the requested rate: average down (a plain decimation filter)
    const ratio = rate / target;
    const n = Math.floor(samples.length / ratio);
    data = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = Math.floor(i * ratio), b = Math.max(a + 1, Math.floor((i + 1) * ratio));
      let sum = 0;
      for (let j = a; j < b && j < samples.length; j++) sum += samples[j];
      data[i] = sum / (b - a);
    }
  }
  const buf = new ArrayBuffer(44 + data.length * 2);
  const v = new DataView(buf);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + data.length * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, target, true); v.setUint32(28, target * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, "data"); v.setUint32(40, data.length * 2, true);
  for (let i = 0; i < data.length; i++) v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, data[i])) * 0x7fff, true);
  return new Blob([buf], { type: "audio/wav" });
}
