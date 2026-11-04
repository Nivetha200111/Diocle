// Types and fetchers for deliveries served by services/api (contracts/delivery.schema.json).
import { API_URL, type Assurance, type Efficiency, type RunEvent } from "./runs";

export type DeliveryStage = "analyzing" | "converting" | "delivering" | "done" | "failed";

export type DeliveryProgram = {
  name: string;
  path?: string;
  status: "queued" | "converting" | "certified" | "not-certified" | "skipped";
  reason?: string | null;
  assurance?: Assurance | null; // convert-anyway deliveries; status stays "not-certified" for everything but "certified"
  costUsd?: number | null;
  runId: string | null;
  run: {
    status: "running" | "certified" | "not-certified";
    stage: string | null;
    events: RunEvent[];
    steps: number;
    before: { passed: number; total: number } | null;
    after: { passed: number; total: number } | null;
    efficiency: Efficiency;
    model: string | null;
    memoryUsed: number | null;
  } | null;
};

// contracts/delivery.schema.json $defs.createTarget (v0.5)
export type CreateTarget = { name: string; owner?: string | null; visibility?: "private" | "public" };

// contracts/delivery.schema.json dependencyTree (v0.9). Labels come from the imported repository: render as text only.
export type DependencyEdge = { from: string; to: string; kind: "call" | "copy" | "job" };
export type DependencyTree = { edges: DependencyEdge[]; total: number; truncated: boolean };

// contracts/delivery.schema.json dependencyDrawing (v0.10). Only status "passed" has a picture.
export type DependencyDrawing = {
  status: "drawing" | "passed" | "failed" | "not-drawn";
  reason?: string | null;
  verified: boolean;
  passedOnAttempt?: number | null;
  part?: { program: string; edges: string[][] } | null;
  attempts: { attempt: number; outcome: string }[];
};

export const dependencyDrawingUrl = (id: string) => `${API_URL}/deliveries/${encodeURIComponent(id)}/dependency-drawing`;

export type Delivery = {
  id: string;
  legacy: { repository: string; commit: string | null };
  target: string | null; // null: a visitor's import, results stay on the site
  createTarget?: CreateTarget; // the delivery was asked to create its target repository
  targetCreated?: boolean; // true once it did (false: not yet, or never)
  public?: boolean;
  convertAnyway?: boolean;
  repoMaxUsd?: number | null;
  spentUsd?: number | null;
  stage: DeliveryStage;
  startedAt: string;
  finishedAt: string | null;
  error: string | null;
  programs: DeliveryProgram[];
  pullRequest: { url: string; checks?: { name: string; state: string; link?: string }[] } | null;
  /** GitHub refused the workflow file, so the delivery was pushed without the re-verify CI: the sentence that says so. */
  ciNotAdded?: string | null;
  /** The analyzer's links, recorded when analysis finishes: absent on older deliveries. */
  dependencyTree?: DependencyTree | null;
  /** One capped Muse Image drawing of a small part of the tree: absent when the engine has it off, and on older deliveries. */
  dependencyDrawing?: DependencyDrawing | null;
  /** Whole-repository build check (contracts/build-report.schema.json, summarised): absent on older deliveries. */
  buildCheck?: {
    verdict: "pass" | "fail" | "warn";
    reasons: string[];
    programs?: number;
    calls?: number;
    copybookDrift?: number;
    classCollisions?: number;
  } | null;
};

export type DeliveryListItem = Pick<Delivery, "id" | "legacy" | "target" | "stage" | "startedAt" | "finishedAt"> & {
  programs: number;
  pullRequest: string | null;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export const fetchDeliveries = () => getJson<DeliveryListItem[]>("/deliveries");
export const fetchDelivery = (id: string) => getJson<Delivery>(`/deliveries/${encodeURIComponent(id)}`);

export type DeliveryRequest = { legacy: string; target?: string; createTarget?: CreateTarget; parallel?: boolean; breaker?: boolean };

export async function startDelivery(body: DeliveryRequest, passcode = ""): Promise<string> {
  const response = await fetch(`${API_URL}/deliveries`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(passcode ? { "X-Diocle-Admin": passcode } : {}) },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data.id as string;
}
