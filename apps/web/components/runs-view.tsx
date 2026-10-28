"use client";

import { useEffect, useState } from "react";
import { Bot, CircleCheck, Coins, ShieldAlert, TriangleAlert } from "lucide-react";
import { API_URL, fetchRun, fetchRuns, type Efficiency, type Run, type RunListItem, type RunMemory, type Verification } from "@/lib/runs";
import { Badge } from "./ui";

const pct = (v: Verification) => (v.total ? Math.round((v.passed / v.total) * 1000) / 10 : 0);
const usd = (n: number | null) => (n === null ? "n/a" : `$${n < 0.01 ? n.toFixed(4) : n.toFixed(2)}`);
const tokens = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`);

function StatCard({ label, value, note, tone, icon }: {
  label: string; value: string; note: string; tone: "green" | "orange" | "purple"; icon: React.ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-top">
        <span>{label}</span>
        <span className={`stat-icon ${tone}`}>{icon}</span>
      </div>
      <div className="stat-value">{value}</div>
      <p>{note}</p>
    </div>
  );
}

const seconds = (ms: number) => (ms >= 60000 ? `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s` : `${Math.round(ms / 1000)}s`);
const shortModel = (m: string | null) => (m ? m.split("/").pop()! : "n/a");
const memoryLabel = (m: RunMemory) => (!m ? "n/a" : !m.enabled ? "off" : `${m.used} in · ${m.learned} new`);

function LessonsPanel({ memory }: { memory: NonNullable<RunMemory> }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Lessons learned</h2>
          <p>Saved to fix memory only because this run passed held-out certification. Later runs get them as hints.</p>
        </div>
      </div>
      <div className="table-scroll">
        <table className="data-table lessons-table">
          <thead><tr><th>Pattern</th><th>What COBOL does</th><th>Java that reproduces it</th></tr></thead>
          <tbody>
            {memory.lessons.map((l) => (
              <tr key={l.pattern}><td>{l.pattern}</td><td>{l.cobol}</td><td className="mono">{l.java}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EfficiencyPanel({ e }: { e: Efficiency }) {
  const perMillion = e.costPer1kLinesUsd === null ? null : e.costPer1kLinesUsd * 1000;
  const rows: [string, string][] = [
    ["Model calls", `${e.modelCalls}`],
    ["Tool steps", `${e.toolSteps}`],
    ["Patches applied", `${e.patchesApplied}`],
    ["Prompt cache hit", `${Math.round(e.cacheHitRate * 100)}%`],
    ["Tokens (in + out)", tokens(e.totalTokens)],
    ["Model time", seconds(e.modelTimeMs)],
    ["COBOL lines", `${e.cobolLines}`],
    ["Cost per 1,000 lines", usd(e.costPer1kLinesUsd)],
  ];
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Agent efficiency</h2>
          <p>What this proof cost. Costs are estimates from list prices.</p>
        </div>
      </div>
      <dl className="eff-grid">
        {rows.map(([k, v]) => (
          <div key={k}><dt>{k}</dt><dd className="mono">{v}</dd></div>
        ))}
      </dl>
      {perMillion !== null && (
        <p className="eff-projection">
          At this rate, 1 million COBOL lines ≈ <strong>{usd(perMillion)}</strong> in model spend
          (straight-line estimate from this one program).
        </p>
      )}
    </section>
  );
}

function EfficiencyTable({ runs, selected, onSelect }: {
  runs: RunListItem[]; selected: string | null; onSelect: (id: string) => void;
}) {
  const [showStopped, setShowStopped] = useState(false);
  const stopped = (r: RunListItem) => !r.certified && r.efficiency.modelCalls === 0;  // interrupted before any model call
  const shown = [...runs].filter((r) => showStopped || !stopped(r))
    .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
  const hidden = runs.filter(stopped).length;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Agent efficiency across runs</h2>
          <p>Newest first. Click a row to open it.{hidden > 0 && <> {" "}
            <button type="button" className="text-button" onClick={() => setShowStopped(!showStopped)}>
              {showStopped ? "Hide" : "Show"} {hidden} interrupted
            </button></>}</p>
        </div>
      </div>
      <div className="table-scroll eff-scroll">
        <table className="data-table eff-table">
          <thead>
            <tr><th>Run</th><th>Model</th><th>Result</th><th>Memory</th><th>Calls</th><th>Steps</th><th>Cache</th>
              <th>Tokens</th><th>Model time</th><th>Cost</th><th>$ / 1k lines</th></tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={r.id === selected ? "selected" : ""} onClick={() => onSelect(r.id)}>
                <td className="mono">{r.program} · {r.createdAt?.slice(5, 16).replace("T", " ")} · {r.command === "run" ? "translate" : "repair"}</td>
                <td className="mono">{shortModel(r.model)}</td>
                <td>{r.certified ? "certified" : "not certified"}</td>
                <td className="mono">{memoryLabel(r.memory)}</td>
                <td className="mono">{r.efficiency.modelCalls}</td>
                <td className="mono">{r.efficiency.toolSteps}</td>
                <td className="mono">{Math.round(r.efficiency.cacheHitRate * 100)}%</td>
                <td className="mono">{tokens(r.efficiency.totalTokens)}</td>
                <td className="mono">{seconds(r.efficiency.modelTimeMs)}</td>
                <td className="mono">{usd(r.efficiency.estimatedCostUsd)}</td>
                <td className="mono">{usd(r.efficiency.costPer1kLinesUsd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function JavaDiff({ diff }: { diff: string }) {
  return (
    <pre className="diff-block">
      {diff.split("\n").map((line, i) => {
        const kind = line.startsWith("@@") ? "diff-hunk" : line.startsWith("+") && !line.startsWith("+++")
          ? "diff-add" : line.startsWith("-") && !line.startsWith("---") ? "diff-del" : "";
        return <span key={i} className={kind}>{line + "\n"}</span>;
      })}
    </pre>
  );
}

function RunDetail({ run }: { run: Run }) {
  const steps = run.events.filter((e) => e.type === "agent-step");
  return (
    <>
      <div className="panel runs-header">
        <div>
          <div className="runs-badges">
            <Badge tone={run.certified ? "green" : "amber"}>{run.certified ? "Certified" : "Not certified"}</Badge>
            <Badge tone="blue" dot={false}>Real run · not a mock</Badge>
          </div>
          <h2>{run.program} · {run.command === "repair" ? "Bring-your-own conversion, repaired" : "Translated, verified and repaired"}</h2>
          <p>
            Java started as: <span className="mono">{run.javaOrigin}</span>
            <br />
            Model: <span className="mono">{run.model ?? "none"}</span> · {run.createdAt?.replace("T", " ")} · run <span className="mono">{run.id}</span>
          </p>
        </div>
      </div>

      <div className="stats-grid">
        <StatCard label="Before" tone="orange" icon={<ShieldAlert size={15} />}
          value={run.before ? `${pct(run.before)}%` : "n/a"}
          note={run.before ? `${run.before.passed}/${run.before.total} cases matched${run.before.stdoutMatch ? "" : " · stdout differs"}` : "not recorded"} />
        <StatCard label="After (held-out inputs)" tone="green" icon={<CircleCheck size={15} />}
          value={run.after ? `${pct(run.after)}%` : "n/a"}
          note={run.after ? `${run.after.passed}/${run.after.total} cases the agent never saw` : "no certification"} />
        <StatCard label="Agent" tone="purple" icon={<Bot size={15} />}
          value={`${steps.length}`} note={`tool steps · ${run.usage.calls} model calls · ${run.rounds.length} round(s)`} />
        <StatCard label="Cost" tone="green" icon={<Coins size={15} />}
          value={usd(run.usage.estimatedCostUsd)}
          note={`${tokens(run.usage.inputTokens)} in (${tokens(run.usage.cachedInputTokens)} cached) · ${tokens(run.usage.outputTokens)} out`} />
      </div>

      <EfficiencyPanel e={run.efficiency} />

      <div className="runs-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Agent trace</h2>
              <p>Every tool call the repair agent made, with its stated reason.</p>
            </div>
            <Badge tone="neutral">{run.model ?? ""}</Badge>
          </div>
          <ol className="trace-list">
            {run.events.map((e, i) =>
              e.type === "agent-step" ? (
                <li key={i} className="trace-step">
                  <span className="trace-num">{e.step}</span>
                  <div>
                    <span className="trace-tool mono">{e.tool}</span>
                    {e.rationale && <p className="trace-why">{e.rationale}</p>}
                    {e.resultSummary && <p className="trace-result mono">→ {e.resultSummary.split("\n")[0]}</p>}
                  </div>
                </li>
              ) : (
                <li key={i} className={`trace-cert ${["memory", "stage"].includes(e.type) ? "memory" : e.type === "breaker" ? (e.broke ? "fail" : "pass") : e.passed ? "pass" : "fail"}`}>
                  {e.type === "certification"
                    ? `Round ${e.round} certification on held-out inputs: ${e.passed ? "PASS" : "FAIL"} · ${e.result?.split("\n")[0]}`
                    : e.message}
                </li>
              ),
            )}
          </ol>
        </section>

        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>What was wrong before</h2>
              <p>Mismatches between GnuCOBOL and the starting Java.</p>
            </div>
            <Badge tone="amber">{run.before?.failed ?? 0} failing</Badge>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Case</th><th>Source</th><th>Difference</th></tr></thead>
              <tbody>
                {(run.before?.failingExamples ?? []).map((f) => (
                  <tr key={f.inputId}>
                    <td className="mono">{f.inputId}</td>
                    <td>{f.inputSource}</td>
                    <td className="mono mismatch runs-diff-cell">{f.diff}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {run.memory && run.memory.lessons.length > 0 && <LessonsPanel memory={run.memory} />}

      {run.javaDiff && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Java changes made by the agent</h2>
              <p>Unified diff from the starting file to the certified result.</p>
            </div>
          </div>
          <JavaDiff diff={run.javaDiff} />
        </section>
      )}
    </>
  );
}

export default function RunsView() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchRuns()
      .then((items) => {
        setRuns(items);
        setSelected((current) => current ?? items[0]?.id ?? null);
      })
      .catch(() => setError("unreachable"));
  }, []);

  useEffect(() => {
    if (!selected) return;
    fetchRun(selected).then(setRun).catch((e: Error) => setError(e.message));
  }, [selected]);

  if (error) {
    return (
      <div className="panel runs-empty">
        <TriangleAlert size={18} />
        <div>
          <h2>Can’t reach the Diocle API at {API_URL}</h2>
          <p>Start it with: <span className="mono">cd services/api &amp;&amp; .venv/bin/uvicorn diocle_api.app:app --port 8000</span></p>
        </div>
      </div>
    );
  }
  if (runs === null) return <div className="panel runs-empty"><p>Loading runs…</p></div>;
  if (runs.length === 0) {
    return (
      <div className="panel runs-empty">
        <p>No runs yet. Create one with <span className="mono">python -m diocle_converter repair samples/interest-accrual</span>.</p>
      </div>
    );
  }
  return (
    <>
      <EfficiencyTable runs={runs} selected={selected} onSelect={setSelected} />
      {run ? <RunDetail run={run} /> : <div className="panel runs-empty"><p>Loading run…</p></div>}
    </>
  );
}
