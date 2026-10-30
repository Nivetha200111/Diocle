// Builds the replay of a recorded run from the data stored with it (run.events, usage.modelCalls, tiers, breaker,
// crosscheck, guard, after). Nothing here is invented: run events carry no timestamps, so the replay follows their recorded
// order, not wall-clock time, and a stage with no events produces no step.
import { callCostUsd, PRICES, type ModelCall, type Run } from "./runs";

export type AgentKey = "translator" | "repair" | "breaker" | "crosscheck" | "guard" | "verifier";

export const AGENTS: { key: AgentKey; name: string; job: string }[] = [
  { key: "translator", name: "Translator", job: "Writes the first Java from the COBOL" },
  { key: "breaker", name: "Breaker", job: "Designs inputs to break the certified Java" },
  { key: "repair", name: "Repair agent", job: "Patches the Java until the checks pass" },
  { key: "crosscheck", name: "Cross-checker", job: "A second model hunts for differences" },
  { key: "guard", name: "Guard", job: "Deterministic policy checks on the Java" },
  { key: "verifier", name: "Verifier (GnuCOBOL)", job: "Runs the original and the Java on the same inputs" },
];

export type Step = {
  id: number;
  agent: AgentKey | null;
  kind: "stage" | "tool" | "breaker" | "escalation" | "certification" | "crosscheck" | "guard";
  title: string;
  detail: string;
  round?: number;
  ms: number;                      // pause before the next step, at 1x
  delta: { agent: AgentKey; tokens: number; usd: number; calls: number } | null;
  tierUp?: { index: number; model: string };  // index into tiers.configured, found by model id
  counterexample?: number;         // last index into run.breaker.counterexamples revealed by this step
  patch?: { rationale: string; text: string; path: string };
  cert?: { passed: boolean; result: string };
};

const roleAgent = (role: string): AgentKey | null =>
  role === "translator" || role === "repair" || role === "breaker" || role === "crosscheck" || role === "guard" ? role : null;

export const callTokens = (c: ModelCall) => c.inputTokens + c.outputTokens;
const cost = (c: ModelCall) => callCostUsd(c) ?? 0;

export function buildSteps(run: Run): Step[] {
  const calls: Record<string, ModelCall[]> = {};
  for (const c of run.usage.modelCalls ?? []) (calls[c.role] ??= []).push(c);
  const take = (role: string): ModelCall | undefined => calls[role]?.shift();
  const steps: Step[] = [];
  const push = (s: Omit<Step, "id" | "delta" | "ms"> & { delta?: Step["delta"]; ms?: number }) =>
    steps.push({ delta: null, ms: 800, ...s, id: steps.length });
  const deltaOf = (agent: AgentKey, cs: (ModelCall | undefined)[]): Step["delta"] => {
    const real = cs.filter((c): c is ModelCall => !!c);
    return real.length ? { agent, tokens: real.reduce((n, c) => n + callTokens(c), 0), usd: real.reduce((n, c) => n + cost(c), 0), calls: real.length } : null;
  };

  const escalations = [...(run.tiers?.escalations ?? [])];
  const configured = run.tiers?.configured ?? [];
  // esc.tier is 1-based, but the model id is the unambiguous key: find the tier by it, falling back to tier - 1.
  const tierIndex = (esc: { tier: number; model: string }) => {
    const i = configured.indexOf(esc.model);
    return i >= 0 ? i : Math.max(0, esc.tier - 1);
  };
  const repairIters = new Set(run.events.filter((e) => e.type === "agent-step").map((e) => `${e.round}:${e.step}`)).size;
  let cxShown = 0;
  let iter = -1;
  let lastIter = "";

  for (const e of run.events) {
    if (e.type === "stage") {
      if (e.stage === "translating") {
        const cs = calls.translator ? calls.translator.splice(0) : [];
        push({ agent: "translator", kind: "stage", title: "Translating", detail: e.message ?? "", delta: deltaOf("translator", cs), ms: 1800 });
      } else if (e.stage === "verifying" || e.stage === "certifying") {
        push({ agent: "verifier", kind: "stage", title: e.stage === "certifying" ? "Certifying on held-out inputs" : "Verifying", detail: e.message ?? "", round: e.round });
      } else if (e.stage === "repairing") {
        push({ agent: "repair", kind: "stage", title: "Repair agent working", detail: e.message ?? "", round: e.round });
      } else if (e.stage === "attacking") {
        push({ agent: "breaker", kind: "stage", title: "Breaker attacking", detail: e.message ?? "" });
      }
    } else if (e.type === "agent-step") {
      const key = `${e.round}:${e.step}`;
      const newIter = key !== lastIter;
      if (newIter) {
        lastIter = key;
        iter++;
        while (escalations.length && escalations[0].round <= (e.round ?? 0)) {
          const esc = escalations.shift()!;
          push({ agent: "repair", kind: "escalation", title: `Escalated to ${tierLabel(esc.model)} (tier ${tierIndex(esc) + 1})`, detail: esc.model, round: e.round, tierUp: { index: tierIndex(esc), model: esc.model }, ms: 1500 });
        }
      }
      // One logged repair call per iteration of the agent loop, in order; any surplus lands on the last iteration.
      const isLast = iter === repairIters - 1;
      const cs: (ModelCall | undefined)[] = [];
      if (newIter) {
        const rc = calls.repair;
        cs.push(take("repair"));
        if (isLast && rc) while (rc.length) cs.push(rc.shift());
      }
      const patch = e.tool === "patch_java" && e.argsSummary
        ? { rationale: e.rationale ?? "", text: String(e.argsSummary.new_text ?? ""), path: String(e.argsSummary.path ?? "") } : undefined;
      const verifierTool = e.tool === "run_differential_test" || e.tool === "compile_java";
      push({
        agent: verifierTool ? "verifier" : "repair", kind: "tool", round: e.round,
        title: `${e.tool}`, detail: e.rationale || (e.resultSummary ?? "").split("\n")[0],
        delta: deltaOf("repair", cs), patch, ms: patch ? 1300 : 650,
        counterexample: cxShown ? cxShown - 1 : undefined,
      });
    } else if (e.type === "certification") {
      push({ agent: "verifier", kind: "certification", title: `Certification round ${e.round ?? 0}`, detail: e.result ?? "", round: e.round,
        cert: { passed: !!e.passed, result: e.result ?? "" }, ms: 1800 });
    } else if (e.type === "breaker") {
      const broke = e.broke ?? 0;
      const cxFrom = cxShown;
      if (broke) cxShown = Math.min(cxShown + broke, run.breaker?.counterexamples.length ?? 0);
      push({ agent: "breaker", kind: "breaker", title: broke ? `Breaker broke the Java (${broke} of ${e.tried}${cxShown > cxFrom ? `; counterexample${cxShown - cxFrom > 1 ? "s" : ""} ${cxFrom + 1}${cxShown - cxFrom > 1 ? ` to ${cxShown}` : ""}` : ""})` : `Breaker found nothing (${e.tried} inputs)`,
        detail: e.message ?? "", round: e.round, delta: deltaOf("breaker", [take("breaker")]),
        counterexample: broke && cxShown ? cxShown - 1 : undefined, ms: 2000 });
    } else if (e.type === "crosscheck") {
      push({ agent: "crosscheck", kind: "crosscheck", title: "Cross-check", detail: e.message ?? "", delta: deltaOf("crosscheck", [take("crosscheck")]), ms: 1500 });
    } else if (e.type === "guard") {
      push({ agent: "guard", kind: "guard", title: e.blocked ? "Guard blocked output" : "Guard checked output", detail: e.message ?? "", delta: deltaOf("guard", [take("guard")]), ms: 1200 });
    }
  }
  // Escalations never reached by an agent step still happened; show them at the end rather than drop them.
  for (const esc of escalations) push({ agent: "repair", kind: "escalation", title: `Escalated to ${tierLabel(esc.model)} (tier ${tierIndex(esc) + 1})`, detail: esc.model, tierUp: { index: tierIndex(esc), model: esc.model }, ms: 1500 });
  return steps;
}

export type Totals = Record<AgentKey, { tokens: number; usd: number; calls: number }>;

export function totalsAt(steps: Step[], n: number): Totals {
  const t = Object.fromEntries(AGENTS.map((a) => [a.key, { tokens: 0, usd: 0, calls: 0 }])) as Totals;
  for (const s of steps.slice(0, n)) if (s.delta) { const x = t[s.delta.agent]; x.tokens += s.delta.tokens; x.usd += s.delta.usd; x.calls += s.delta.calls; }
  return t;
}

// What each role actually used over the whole run, from the logged model calls.
export function castStats(run: Run) {
  const out: Record<string, { models: string[]; calls: number; tokens: number; usd: number }> = {};
  for (const c of run.usage.modelCalls ?? []) {
    const a = roleAgent(c.role) ?? "other";
    const o = (out[a] ??= { models: [], calls: 0, tokens: 0, usd: 0 });
    if (!o.models.includes(c.model)) o.models.push(c.model);
    o.calls++; o.tokens += callTokens(c); o.usd += cost(c);
  }
  return out;
}

// A readable tier name derived from the model id (no hardcoded list): "muse-wonder-1.0" -> "wonder 1.0".
export const tierLabel = (model: string) => model.replace(/^.*muse-/, "").replace(/-/g, " ");
export const priceOf = (model: string) => PRICES[model] ?? null;

// A run is worth replaying when it recorded something beyond a plain translation.
export const hasTeamData = (r: Run) =>
  !!(r.breaker || r.crosscheck || r.tiers?.enabled) && r.events.length > 0;
