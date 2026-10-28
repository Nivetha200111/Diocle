"use client";

import { useEffect, useState } from "react";
import { ExternalLink, GitPullRequest, TriangleAlert } from "lucide-react";
import { API_URL } from "@/lib/runs";
import { fetchDeliveries, fetchDelivery, type Delivery, type DeliveryListItem, type DeliveryProgram } from "@/lib/deliveries";

type Led = "off" | "busy" | "ok" | "bad";

const repoName = (url: string) => url.replace("https://github.com/", "");
const usd = (n: number | null | undefined) => (n == null ? "n/a" : `$${n.toFixed(4)}`);

function elapsed(from: string, to: string | null, now: number) {
  const ms = (to ? Date.parse(to) : now) - Date.parse(from);
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function ciState(d: Delivery): Led {
  const checks = d.pullRequest?.checks ?? [];
  if (!d.pullRequest) return "off";
  if (checks.length === 0) return "busy";
  if (checks.some((c) => ["FAILURE", "ERROR", "CANCELLED", "TIMED_OUT"].includes(c.state))) return "bad";
  if (checks.every((c) => c.state === "SUCCESS")) return "ok";
  return "busy";
}

function stages(d: Delivery): { label: string; detail: string; led: Led }[] {
  const order = ["analyzing", "converting", "delivering", "done"];
  const at = d.stage === "failed" ? -1 : order.indexOf(d.stage);
  const led = (i: number): Led => (d.stage === "failed" && i === Math.max(0, order.indexOf("converting")) ? "bad"
    : at > i ? "ok" : at === i ? "busy" : "off");
  const certified = d.programs.filter((p) => p.status === "certified").length;
  const ci = ciState(d);
  return [
    { label: "1. Clone & analyze", detail: d.legacy.commit ? `@${d.legacy.commit.slice(0, 12)} · ${d.programs.length} programs` : "reading copybooks and JCL", led: led(0) },
    { label: "2. Convert & certify", detail: `${certified}/${d.programs.length} certified`, led: led(1) },
    { label: "3. Open pull request", detail: d.pullRequest ? "opened" : "waiting", led: d.pullRequest ? "ok" : led(2) },
    { label: "4. CI re-verifies", detail: ci === "ok" ? "passed on fresh inputs" : ci === "bad" ? "failed" : ci === "busy" ? "running" : "waiting", led: ci },
  ];
}

function programLed(p: DeliveryProgram): Led {
  return p.status === "certified" ? "ok" : p.status === "converting" ? "busy" : p.status === "queued" ? "off" : "bad";
}

function ProgramCard({ p }: { p: DeliveryProgram }) {
  const run = p.run;
  return (
    <section className="panel dlv-program">
      <div className="panel-heading">
        <div>
          <h2><span className={`led led-${programLed(p)}`} /> {p.name}</h2>
          <p>{p.path ?? ""} · {p.status}{run?.stage && p.status === "converting" ? ` · ${run.stage}` : ""}</p>
        </div>
      </div>
      <ol className="trace-list dlv-log">
        {!run && <li className="dlv-idle">{p.status === "queued" ? "waiting for its turn…" : "no run recorded"}</li>}
        {run?.events.map((e, i) => (
          <li key={i} className="dlv-line">
            {e.type === "agent-step" ? (
              <><span className="trace-tool">{e.tool}</span> {e.rationale ? <span className="trace-why">{e.rationale}</span> : null}</>
            ) : e.type === "certification" ? (
              <strong>{e.passed ? "CERTIFIED" : "CERTIFICATION FAILED"} · {e.result?.split("\n")[0]}</strong>
            ) : (
              <span>» {e.message}</span>
            )}
          </li>
        ))}
        {run?.status === "running" && <li className="dlv-line dlv-cursor">_</li>}
      </ol>
      {run && (
        <p className="dlv-stats mono">
          {run.before ? `before ${run.before.passed}/${run.before.total}` : "before …"} → {run.after ? `held-out ${run.after.passed}/${run.after.total}` : "held-out …"}
          {" · "}{run.efficiency.modelCalls} calls · {run.steps} steps · {usd(run.efficiency.estimatedCostUsd)}
          {run.memoryUsed ? ` · ${run.memoryUsed} lessons from memory` : ""}
        </p>
      )}
    </section>
  );
}

export default function DeliveryView() {
  const [list, setList] = useState<DeliveryListItem[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const load = () => fetchDeliveries().then((items) => {
      setList(items);
      setSelected((current) => current ?? items[0]?.id ?? null);
    }).catch(() => setError("unreachable"));
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!selected) return;
    let stop = false;
    const tick = async () => {
      try {
        const d = await fetchDelivery(selected);
        if (!stop) setDelivery(d);
      } catch (e) {
        if (!stop) setError((e as Error).message);
      }
    };
    tick();
    const t = setInterval(tick, 2000);
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => { stop = true; clearInterval(t); clearInterval(clock); };
  }, [selected]);

  if (error) {
    return (
      <div className="panel runs-empty">
        <TriangleAlert size={18} />
        <div><h2>Can’t reach the Diocle API at {API_URL}</h2><p>Start services/api, then reload.</p></div>
      </div>
    );
  }
  if (list === null) return <div className="panel runs-empty"><p>Loading deliveries…</p></div>;
  if (list.length === 0) {
    return (
      <div className="panel runs-empty">
        <p>No deliveries yet. Start one with <span className="mono">python -m diocle_api.deliver LEGACY_URL TARGET_URL</span>.</p>
      </div>
    );
  }
  if (!delivery) return <div className="panel runs-empty"><p>Loading delivery…</p></div>;

  const running = !["done", "failed"].includes(delivery.stage);
  return (
    <>
      <section className="panel runs-header dlv-header">
        <div>
          <div className="runs-badges">
            <span className={`badge ${running ? "badge-amber" : delivery.stage === "done" ? "badge-green" : "badge-amber"}`}>
              {running ? "● LIVE" : delivery.stage === "done" ? "Delivered" : "Failed"}
            </span>
            <span className="badge badge-blue">Real run · not a mock</span>
            {list.length > 1 && (
              <select className="dlv-select" value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
                {list.map((d) => <option key={d.id} value={d.id}>{d.id} · {d.stage}</option>)}
              </select>
            )}
          </div>
          <h2>
            <a href={delivery.legacy.repository} target="_blank" rel="noreferrer">{repoName(delivery.legacy.repository)}</a>
            {"  →  "}
            <a href={delivery.target} target="_blank" rel="noreferrer">{repoName(delivery.target)}</a>
          </h2>
          <p>
            COBOL in, certified Java out as a pull request. Elapsed <span className="mono">{elapsed(delivery.startedAt, delivery.finishedAt, now)}</span>
            {delivery.error ? ` · error: ${delivery.error}` : ""}
          </p>
        </div>
      </section>

      <div className="dlv-stages">
        {stages(delivery).map((s) => (
          <div key={s.label} className={`dlv-stage dlv-${s.led}`}>
            <span className={`led led-${s.led}`} />
            <div><strong>{s.label}</strong><small>{s.detail}</small></div>
          </div>
        ))}
      </div>

      <div className="dlv-grid">
        {delivery.programs.map((p) => <ProgramCard key={p.name} p={p} />)}
      </div>

      {delivery.pullRequest && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2><GitPullRequest size={14} /> Pull request</h2>
              <p>Opened on {repoName(delivery.target)}. CI re-runs the proof on fresh inputs Diocle never saw.</p>
            </div>
          </div>
          <div className="dlv-pr">
            <a className="button primary" href={delivery.pullRequest.url} target="_blank" rel="noreferrer">
              Open {delivery.pullRequest.url.split("/").slice(-2).join(" #")} <ExternalLink size={13} />
            </a>
            <ul>
              {(delivery.pullRequest.checks ?? []).length === 0 && <li><span className="led led-busy" /> waiting for CI to start…</li>}
              {(delivery.pullRequest.checks ?? []).map((c) => (
                <li key={c.name}>
                  <span className={`led led-${c.state === "SUCCESS" ? "ok" : ["FAILURE", "ERROR", "CANCELLED"].includes(c.state) ? "bad" : "busy"}`} />
                  {c.link ? <a href={c.link} target="_blank" rel="noreferrer">{c.name}</a> : c.name} · {c.state.toLowerCase()}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
