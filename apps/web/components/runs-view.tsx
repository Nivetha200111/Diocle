"use client";

import { useEffect, useState } from "react";
import { Bot, CircleCheck, Coins, ShieldAlert, TriangleAlert } from "lucide-react";
import { API_URL, ASSURANCE_BADGE, callCostUsd, fetchRun, fetchRunSchema, fetchRunSource, fetchRuns, hostOf, isInterrupted, isPrivateModel, reverifyRun, schemaFile, type Breaker, type Crosscheck, type Efficiency, type Tiers, type Guard, type GuardFinding, type ModelCall, type Reverify, type Run, type RunListItem, type RunMemory, type RunSource, type SourceFile, type Verification } from "@/lib/runs";
import { AssuranceBadge, AssuranceNote } from "./assurance";
import { SAMPLE_RUN, SUPERSEDED } from "@/lib/config";
import { Badge, PrivateModeBadge, Skeleton } from "./ui";
import { PlainEnglishCard } from "./plain-english";
import { BehaviorPanel } from "./behavior-panel";
import { DatabasePanel } from "./database-panel";
import { ReproducerPanel } from "./reproducer-panel";

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

function BreakerPanel({ b }: { b: Breaker }) {
  return (
    <section className={`panel breaker-panel ${b.broke ? "breaker-broke" : ""}`}>
      <div className="panel-heading">
        <div>
          <h2><ShieldAlert size={14} /> Breaker agent</h2>
          <p>
            After certification, a second Muse Spark agent designed {b.tried} inputs to break the Java
            over {b.rounds} round(s).{" "}
            {b.broke
              ? `${b.broke} broke it${b.fixed ? `; the repair agent fixed them and the Java re-certified on fresh held-out inputs.` : "; not yet fixed."}`
              : "None broke it."}
          </p>
        </div>
      </div>
      {b.counterexamples.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Designed input</th><th>Why the agent tried it</th><th>What differed</th></tr></thead>
            <tbody>
              {b.counterexamples.map((c, i) => (
                <tr key={i}>
                  <td className="mono">{c.input}</td>
                  <td>{c.why}</td>
                  <td className="mono">{c.diff}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// Model tiers: which model the repair agent used when, with the hard caps on the stronger (pricier) models.
function TiersPanel({ t }: { t: Tiers }) {
  const ups = t.escalations ?? [];
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Model tiers</h2>
          <p>
            Tier 1 {t.configured?.[0]} writes and repairs first.{" "}
            {ups.length
              ? `After a failed certification round the repair agent moved up: ${ups.map((u) => `round ${u.round} on ${u.model}`).join(", ")}.`
              : "It never needed a higher tier."}{" "}
            {t.breakerModel ? `The breaker attacked with ${t.breakerModel}. ` : ""}
            Calls above tier 1 are capped at {t.capCalls} calls and ${t.capUsd?.toFixed(2)} per run; this run used {t.escalatedCalls ?? 0} calls
            (about ${(t.escalatedUsd ?? 0).toFixed(4)}; a model with no known price counts as the whole cap).
          </p>
        </div>
      </div>
    </section>
  );
}

function CrosscheckPanel({ c }: { c: Crosscheck }) {
  if (c.skipped) return null;  // the model card already shows the role as not needed; the trace says why it was skipped
  const found = c.mismatches ?? 0;
  return (
    <section className={`panel breaker-panel ${found ? "breaker-broke" : ""}`}>
      <div className="panel-heading">
        <div>
          <h2><ShieldAlert size={14} /> Independent check · Muse Spark Open (open weights)</h2>
          <p>
            After certification, a different model ({c.model}) read the COBOL and the Java and proposed {c.casesProposed ?? 0} inputs;
            {" "}{c.casesValid ?? 0} fit the layout and were run through GnuCOBOL and the Java.{" "}
            {found
              ? `${found} really differed${c.fixed ? "; the repair agent fixed them and the Java re-certified." : "; not yet fixed."}`
              : "None differed."}{" "}
            The model&apos;s opinion certifies nothing; only the comparison does.
          </p>
        </div>
      </div>
      {(c.suspected?.length ?? 0) > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Field it suspected</th><th>Its concern (opinion, not evidence)</th></tr></thead>
            <tbody>{c.suspected!.map((x, i) => <tr key={i}><td className="mono">{x.field}</td><td>{x.concern}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

const ROLES: [string, string, string][] = [
  ["translator", "Translator", "writes the first Java from the COBOL"],
  ["repair", "Repair agent", "reads failures, patches, compiles, re-tests"],
  ["breaker", "Breaker agent", "designs inputs to break certified Java"],
  ["crosscheck", "Independent check", "a second, open-weight model hunts for a divergence"],
  ["document", "Documenter", "writes claims about the COBOL; GnuCOBOL checks them"],
  ["guard", "Guard agent", "reviews the final Java for leaks and test gaming; can revoke certification"],
];

const where = (f: GuardFinding) => (f.file ? `${f.file}${f.line ? `:${f.line}` : ""}` : f.line ? `line ${f.line}` : "");

// The guard agent: its policy runs before any Java executes; its model review reads the final Java next to the COBOL.
function GuardPanel({ g }: { g: Guard }) {
  const review = g.review;
  const findings = [...g.policy.map((f) => ({ ...f, by: "policy" })), ...(g.sourceFlags ?? []).map((f) => ({ ...f, by: "policy (COBOL)" })),
    ...(review?.findings ?? []).map((f) => ({ ...f, by: "review" }))];
  return (
    <section className={`panel breaker-panel ${g.blocked ? "breaker-broke" : ""}`}>
      <div className="panel-heading">
        <div>
          <h2><ShieldAlert size={14} /> Guard agent</h2>
          <p>
            {g.blocked ? "Blocked: this run is not certified because of the guard. " : ""}
            The policy checked the Java before every test{g.stopped ? ` and refused to run it ${g.stopped} time(s); the repair agent was told why` : " and found nothing it had to stop"}.{" "}
            {review
              ? review.verdict === "error"
                ? `The model review (${review.model}) did not complete (${review.summary}); certification stands on the tests and the policy.`
                : `Model review by ${review.model} on ${hostOf(review.model)}: ${review.verdict.toUpperCase()}. ${review.summary}`
              : "No model review in this run (policy only, or the run was not certified)."}
            {" "}The policy is a speed bump; the sandbox is the boundary.
          </p>
        </div>
      </div>
      {findings.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Severity</th><th>Found by</th><th>Kind</th><th>Where</th><th>What</th></tr></thead>
            <tbody>
              {findings.map((f, i) => (
                <tr key={i}>
                  <td>{f.severity}</td><td>{f.by}</td><td>{f.category}</td>
                  <td className="mono">{where(f)}</td><td>{f.explanation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

// Which Meta model did what in this run, from the logged calls: role → model ID → tokens → cost.
function ModelCard({ run }: { run: Run }) {
  const calls = run.usage.modelCalls ?? [];
  if (calls.length === 0) return null;
  const rows = ROLES.map(([role, label, does]) => {
    const mine = calls.filter((c: ModelCall) => c.role === role);
    const costs = mine.map(callCostUsd);
    return {
      role, label, does, calls: mine.length,
      models: [...new Set(mine.map((c) => c.model))],
      modes: [...new Set(mine.map((c) => c.mode))],
      tokensIn: mine.reduce((n, c) => n + c.inputTokens, 0),
      tokensOut: mine.reduce((n, c) => n + c.outputTokens, 0),
      cost: costs.some((c) => c === null) ? null : costs.reduce<number>((n, c) => n + (c ?? 0), 0),
    };
  });
  return (
    <section className="panel model-card">
      <div className="panel-heading">
        <div>
          <h2>Meta models in this run</h2>
          <p>Every model call is logged with its role. No other model is used anywhere in Diocle. Run total: {run.usage.estimatedCostUsd === null ? "n/a" : `$${run.usage.estimatedCostUsd.toFixed(4)}`}.</p>
        </div>
        {isPrivateModel(run.model) && <PrivateModeBadge host={hostOf(run.model ?? "")} />}
      </div>
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>Role</th><th>Model ID</th><th>Served by</th><th>Calls</th><th>Tokens in / out</th><th>Est. cost</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.role} className={r.calls ? "" : "model-card-idle"}>
                <td><strong>{r.label}</strong><br /><small>{r.does}</small></td>
                <td className="mono">{r.models.join(", ") || "not needed in this run"}</td>
                <td>{r.models.map((m) => (isPrivateModel(m) ? `${hostOf(m)} (open weights)` : hostOf(m))).join(", ")}</td>
                <td className="mono">{r.calls}</td>
                <td className="mono">{r.calls ? `${tokens(r.tokensIn)} / ${tokens(r.tokensOut)}` : ""}</td>
                <td className="mono">{r.calls ? (r.cost === null ? "n/a" : `$${r.cost.toFixed(4)}`) : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// The original COBOL next to the Java this run produced, so a reader can compare them line by line.
function SourcePanel({ run }: { run: Run }) {
  const [source, setSource] = useState<RunSource | null>(null);
  const [failed, setFailed] = useState(false);
  const [cobolFile, setCobolFile] = useState(0);
  const [javaFile, setJavaFile] = useState(0);
  const [sql, setSql] = useState<SourceFile | null>(null);
  useEffect(() => {
    setSource(null);
    setFailed(false);
    setCobolFile(0);
    setJavaFile(0);
    setSql(null);
    if (run.visitor) return;
    let live = true;  // a slow answer for the previous run must not land next to this run's Java
    fetchRunSource(run.id).then((s) => live && setSource(s)).catch(() => live && setFailed(true));
    fetchRunSchema(run.id).then((s) => live && setSql(schemaFile(s))).catch(() => live && setSql(null));  // older engines: Java only
    return () => {
      live = false;
    };
  }, [run.id, run.visitor]);
  if (run.visitor || failed) return null;  // visitor code is not served; the trace and diff below still tell the story
  if (!source) return <Skeleton rows={4} label="Loading the COBOL and the Java" />;
  if (source.cobol.length === 0 && source.java.length === 0) return null;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>COBOL next to Java</h2>
          <p>Left: the original program and its copybooks. Right: the Java {run.certified ? "that was certified" : "as the run left it"}
            {sql ? ", and the copybooks as SQL tables (schema.sql)" : ""}.</p>
        </div>
      </div>
      <div className="source-split">
        <SourcePane label="COBOL" files={source.cobol} at={cobolFile} pick={setCobolFile} />
        <SourcePane label={sql ? "JAVA · SQL" : "JAVA"} files={sql ? [...source.java, sql] : source.java} at={javaFile} pick={setJavaFile} />
      </div>
    </section>
  );
}

export function SourcePane({ label, files, at = 0, pick, placeholder }: {
  label: string; files: RunSource["cobol"]; at?: number; pick?: (i: number) => void; placeholder?: string;
}) {
  const file = files[at];
  return (
    <div className="source-pane">
      <div className="source-tabs" role="tablist" aria-label={`${label} files`}>
        <span className="source-lang">{label}</span>
        {files.map((f, i) => (
          <button key={f.path} type="button" role="tab" aria-selected={i === at} className={i === at ? "active" : ""}
                  onClick={() => pick?.(i)}>
            {f.path.split("/").pop()}
          </button>
        ))}
      </div>
      <pre className="source-code">{file ? file.text + (file.truncated ? "\n… (truncated)" : "") : placeholder ?? "not recorded"}</pre>
    </div>
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
  const [allColumns, setAllColumns] = useState(false);
  const stopped = (r: RunListItem) => isInterrupted(r)
    || (r.status !== "running" && !r.certified && r.efficiency.modelCalls === 0);  // interrupted
  const shown = [...runs].filter((r) => showStopped || !stopped(r))
    .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""));
  const hidden = runs.filter(stopped).length;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Agent efficiency across runs</h2>
          <p>Newest first. Click a row to open it.{" "}
            <button type="button" className="text-button" onClick={() => setAllColumns(!allColumns)}>
              {allColumns ? "Fewer columns" : "Show all columns"}
            </button>
            {hidden > 0 && <>{" "}
            <button type="button" className="text-button" onClick={() => setShowStopped(!showStopped)}>
              {showStopped ? "Hide" : "Show"} {hidden} interrupted
            </button></>}</p>
        </div>
      </div>
      <div className="table-scroll eff-scroll">
        <table className="data-table eff-table">
          <thead>
            {allColumns
              ? <tr><th>Run</th><th>Model</th><th>Result</th><th>Memory</th><th>Calls</th><th>Steps</th><th>Cache</th>
                  <th>Tokens</th><th>Model time</th><th>Cost</th><th>$ / 1k lines</th></tr>
              : <tr><th>Run</th><th>Model</th><th>Result</th><th>Calls</th><th>Cost</th></tr>}
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={r.id === selected ? "selected" : ""} onClick={() => onSelect(r.id)}>
                <td className="mono">{r.program} · {r.createdAt?.slice(5, 16).replace("T", " ")} · {r.command === "run" ? "translate" : "repair"}</td>
                <td className="mono">{r.model ? shortModel(r.model) : "none yet"}</td>
                <td>{isInterrupted(r) ? "interrupted (engine restarted)" : r.status === "running" ? "running…" : r.certified ? "certified" : r.assurance ? ASSURANCE_BADGE[r.assurance].label.toLowerCase() : "not certified"}{r.visitor ? " · visitor import" : ""}{SUPERSEDED[r.id] ? " · superseded" : ""}</td>
                {allColumns && <td className="mono">{memoryLabel(r.memory)}</td>}
                <td className="mono">{r.efficiency.modelCalls}</td>
                {allColumns && <>
                  <td className="mono">{r.efficiency.toolSteps}</td>
                  <td className="mono">{Math.round(r.efficiency.cacheHitRate * 100)}%</td>
                  <td className="mono">{tokens(r.efficiency.totalTokens)}</td>
                  <td className="mono">{seconds(r.efficiency.modelTimeMs)}</td>
                </>}
                <td className="mono">{usd(r.efficiency.estimatedCostUsd)}</td>
                {allColumns && <td className="mono">{usd(r.efficiency.costPer1kLinesUsd)}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ReverifyPanel({ run }: { run: Run }) {
  const [result, setResult] = useState<Reverify | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!run.certified) return null;
  if (run.visitor) {
    return (
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Visitor import</h2>
            <p>This program came from a repository Diocle does not control. Its result is shown as the sandbox reported it and is not offered for re-verification here.</p>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Check it yourself</h2>
          <p>Re-run the original COBOL and this Java on 1,000 inputs from a seed chosen now. No model is involved.</p>
        </div>
      </div>
      <div className="reverify">
        <button className="button primary" disabled={busy} onClick={async () => {
          setBusy(true);
          setError("");
          try {
            setResult(await reverifyRun(run.id));
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}>{busy ? "Running both programs…" : "Re-verify on a fresh seed"}</button>
        {result && (
          <p className={`reverify-result ${result.allMatch ? "ok" : "bad"}`}>
            {result.allMatch ? "PASS" : "FAIL"} · {result.passed}/{result.total} cases match ·
            stdout {result.stdoutMatch ? "matches" : "differs"} · exit code {result.exitCodeMatch ? "matches" : "differs"} ·
            seed {result.seed} · {result.seconds}s
            {result.firstMismatch && <><br />First difference: {result.firstMismatch}</>}
          </p>
        )}
        {error && <p className="reverify-result bad">{error}</p>}
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
      {run.assurance && <AssuranceNote assurance={run.assurance} reason={run.assuranceReason} repair={run.cobolRepair} />}
      <div className="panel runs-header">
        <div>
          <div className="runs-badges">
            {run.assurance && run.assurance !== "certified"
              ? <AssuranceBadge assurance={run.assurance} reason={run.assuranceReason} />
              : <Badge tone={run.certified ? "green" : "amber"}>{run.certified ? "Certified" : "Not certified"}</Badge>}
            {isPrivateModel(run.model) && <PrivateModeBadge host={hostOf(run.model ?? "")} />}
            {run.guard?.blocked && <Badge tone="amber">Blocked by the guard</Badge>}
            {run.guard?.review?.verdict === "error" && <Badge tone="amber">Guard review unavailable</Badge>}
          </div>
          <h2>{run.program} · {run.command === "repair"
            ? (steps.length ? "Bring-your-own conversion, repaired" : "Bring-your-own conversion, verified")
            : (steps.length ? "Translated, verified and repaired" : "Translated and verified (no repair needed)")}</h2>
          <p>
            Java started as: <span className="mono">{run.javaOrigin}</span>
            <br />
            Model: <span className="mono">{run.model ?? "none"}</span> · {run.createdAt?.replace("T", " ")} · run <span className="mono">{run.id}</span>
          </p>
          {SUPERSEDED[run.id] && <p className="dlv-reason">{SUPERSEDED[run.id]}</p>}
        </div>
      </div>

      <PlainEnglishCard run={run} />

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

      {run.breaker && <BreakerPanel b={run.breaker} />}
      <ReproducerPanel runId={run.id} expected={!run.visitor && ((run.reproducers?.length ?? 0) > 0 || (run.breaker?.broke ?? 0) > 0)} />
      {run.crosscheck && <CrosscheckPanel c={run.crosscheck} />}
      {run.behavior && <BehaviorPanel b={run.behavior} />}
      {run.after?.database && <DatabasePanel d={run.after.database} />}
      {run.tiers?.enabled && <TiersPanel t={run.tiers} />}

      {run.guard && <GuardPanel g={run.guard} />}

      <ReverifyPanel run={run} />

      <SourcePanel run={run} />

      <ModelCard run={run} />

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
                <li key={i} className={`trace-cert ${["memory", "stage"].includes(e.type) ? "memory" : ["breaker", "crosscheck"].includes(e.type) ? (e.broke ? "fail" : "pass") : e.type === "guard" ? (e.blocked ? "fail" : "memory") : e.passed ? "pass" : "fail"}`}>
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
              <p>
                {!run.before
                  ? "No verification of the starting Java was recorded for this run."
                  : run.before.failed === 0
                    ? `The starting Java already matched GnuCOBOL on all ${run.before.total} test inputs, so no repair was needed.`
                    : "Mismatches between GnuCOBOL and the starting Java."}
              </p>
            </div>
            {run.before && <Badge tone={run.before.failed === 0 ? "green" : "amber"}>{run.before.failed === 0 ? "all matched" : `${run.before.failed} failing`}</Badge>}
          </div>
          {(run.before?.failed ?? 0) > 0 && (
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
          )}
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
    const fromHash = () => (window.location.hash.startsWith("#run=") ? decodeURIComponent(window.location.hash.slice(5)) : null);
    fetchRuns()
      .then((items) => {
        setRuns(items);
        // With no link to a run, open the front-page sample (the breaker story) if this engine has it.
        const sample = items.find((r) => r.id === SAMPLE_RUN.id)?.id;
        setSelected((current) => fromHash() ?? current ?? sample ?? items[0]?.id ?? null);
      })
      .catch(() => setError("unreachable"));
    const follow = () => {
      const id = fromHash();
      if (id) setSelected(id);
    };
    window.addEventListener("hashchange", follow);
    return () => window.removeEventListener("hashchange", follow);
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
  if (runs === null) return <><Skeleton rows={6} label="Loading runs" /><Skeleton rows={3} label="Loading run" /></>;
  if (runs.length === 0) {
    return (
      <div className="panel runs-empty">
        <p>No runs yet. Create one with <span className="mono">python -m diocle_converter repair samples/interest-accrual</span>.</p>
      </div>
    );
  }
  return (
    <>
      <EfficiencyTable runs={runs} selected={selected} onSelect={(id) => {
        setSelected(id);
        window.history.replaceState(null, "", `#run=${encodeURIComponent(id)}`);  // the address now links to this run
      }} />
      {run && run.id === selected ? <RunDetail run={run} /> : <Skeleton rows={4} label="Loading run" />}
    </>
  );
}
