"use client";

import { useEffect, useState } from "react";
import { Bot, CircleCheck, Coins, ShieldAlert, TriangleAlert } from "lucide-react";
import { API_URL, fetchRun, fetchRuns, type Run, type RunListItem, type Verification } from "@/lib/runs";
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
                <li key={i} className={`trace-cert ${e.passed ? "pass" : "fail"}`}>
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
      {runs.length > 1 && (
        <div className="tabs runs-tabs" role="tablist" aria-label="Runs">
          {runs.map((r) => (
            <button key={r.id} role="tab" aria-selected={r.id === selected}
              className={r.id === selected ? "active" : ""} onClick={() => setSelected(r.id)}>
              {r.program} · {r.createdAt?.slice(5, 16).replace("T", " ")} · {r.certified ? "certified" : "not certified"}
            </button>
          ))}
        </div>
      )}
      {run ? <RunDetail run={run} /> : <div className="panel runs-empty"><p>Loading run…</p></div>}
    </>
  );
}
