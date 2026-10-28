// Types and fetchers for deliveries served by services/api (contracts/delivery.schema.json).
import { API_URL, type Efficiency, type RunEvent } from "./runs";

export type DeliveryStage = "analyzing" | "converting" | "delivering" | "done" | "failed";

export type DeliveryProgram = {
  name: string;
  path?: string;
  status: "queued" | "converting" | "certified" | "not-certified" | "skipped";
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

export type Delivery = {
  id: string;
  legacy: { repository: string; commit: string | null };
  target: string;
  stage: DeliveryStage;
  startedAt: string;
  finishedAt: string | null;
  error: string | null;
  programs: DeliveryProgram[];
  pullRequest: { url: string; checks?: { name: string; state: string; link?: string }[] } | null;
};

export type DeliveryListItem = Pick<Delivery, "id" | "legacy" | "target" | "stage" | "startedAt" | "finishedAt"> & {
  programs: number;
  pullRequest: string | null;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

export const fetchDeliveries = () => getJson<DeliveryListItem[]>("/deliveries");
export const fetchDelivery = (id: string) => getJson<Delivery>(`/deliveries/${encodeURIComponent(id)}`);
