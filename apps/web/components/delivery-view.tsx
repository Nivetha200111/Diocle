"use client";

import { useEffect, useRef, useState } from "react";
import { ExternalLink, GitPullRequest, Plus, TriangleAlert } from "lucide-react";
import { API_URL } from "@/lib/runs";
import { CANONICAL, LINKS, useApiConfig } from "@/lib/config";
import { Skeleton } from "./ui";
import { fetchDeliveries, fetchDelivery, startDelivery, type Delivery, type DeliveryListItem, type DeliveryProgram } from "@/lib/deliveries";

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
  if (!d.target) {
    return [
      { label: "1. Clone & analyze", detail: d.legacy.commit ? `@${d.legacy.commit.slice(0, 12)} · ${d.programs.length} programs` : "reading copybooks and JCL", led: led(0) },
      { label: "2. Convert & certify", detail: `${certified}/${d.programs.filter((p) => p.status !== "skipped").length} certified`, led: led(1) },
      { label: "3. Results", detail: d.stage === "done" ? "Java, diffs and traces in Live runs" : "waiting", led: d.stage === "done" ? "ok" : "off" },
    ];
  }
  return [
    { label: "1. Clone & analyze", detail: d.legacy.commit ? `@${d.legacy.commit.slice(0, 12)} · ${d.programs.length} programs` : "reading copybooks and JCL", led: led(0) },
    { label: "2. Convert & certify", detail: `${certified}/${d.programs.length} certified`, led: led(1) },
    { label: "3. Open pull request", detail: d.pullRequest ? "opened" : "waiting", led: d.pullRequest ? "ok" : led(2) },
    { label: "4. CI re-verifies", detail: ci === "ok" ? "passed on fresh inputs" : ci === "bad" ? "failed" : ci === "busy" ? "running" : "waiting", led: ci },
  ];
}

// Why a delivery failed, in words a reader can act on. A refusal to certify is the product working; an engine
// error after every program certified is not a verdict on the code.
function failureReason(d: Delivery, list: DeliveryListItem[]): string | null {
  if (d.stage !== "failed") return null;
  const tried = d.programs.filter((p) => p.status !== "skipped");
  const refused = tried.filter((p) => p.status === "not-certified").map((p) => p.name);
  const later = list.find((o) => o.stage === "done" && o.legacy.repository === d.legacy.repository
    && o.target === d.target && o.startedAt > d.startedAt);
  const retried = later ? ` A later delivery of the same repository (${later.id}) completed.` : "";
  if (refused.length) {
    return `The verifier refused to certify ${refused.join(", ")}: Diocle opens no pull request for code that does not match the original. This is the product working.${retried}`;
  }
  if (tried.length && tried.every((p) => p.status === "certified")) {
    return `Every program was certified; then an engine error stopped the delivery${d.error ? ` (${d.error})` : ""}, so no pull request came from this attempt.${retried}`;
  }
  return `Stopped before every program finished${d.error ? `: ${d.error}` : ""}.${retried}`;
}

// The page heading's "New delivery" button: disabled, with the reason, while it could not start anything.
export function NewDeliveryButton({ onClick }: { onClick: () => void }) {
  const config = useApiConfig();
  const [running, setRunning] = useState<string | null>(null);
  useEffect(() => {
    const load = () => fetchDeliveries()
      .then((items) => setRunning(items.find((d) => !["done", "failed"].includes(d.stage))?.id ?? null))
      .catch(() => setRunning(null));
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, []);
  const imports = config?.publicImports;
  const reason = running ? `${running} is running; one job at a time`
    : imports?.enabled && !imports.budgetLeft ? "today's conversion budget is used up" : null;
  return (
    <div className="new-delivery">
      <button className="button primary" disabled={!!reason} onClick={onClick}>
        <Plus size={17} />
        New delivery
      </button>
      {reason && <small className="new-delivery-reason">{reason}</small>}
    </div>
  );
}

function programLed(p: DeliveryProgram): Led {
  return p.status === "certified" ? "ok" : p.status === "converting" ? "busy" : p.status === "queued" ? "off" : "bad";
}

function ProgramCard({ p }: { p: DeliveryProgram }) {
  const run = p.run;
  const log = useRef<HTMLOListElement>(null);
  const last = run?.events.length ? JSON.stringify(run.events[run.events.length - 1]) : "";  // the API sends the newest few
  useEffect(() => {
    // Live: follow the newest line. Finished: bring the verdict (the last certification line) into view.
    const box = log.current;
    if (!box) return;
    const verdict = [...box.querySelectorAll<HTMLElement>(".dlv-ev-certification")].pop();
    if (run?.status !== "running" && verdict) {
      box.scrollTop += verdict.getBoundingClientRect().top - box.getBoundingClientRect().top - 8;
    } else {
      box.scrollTop = box.scrollHeight;
    }
  }, [last, run?.status]);
  return (
    <section className="panel dlv-program">
      <div className="panel-heading">
        <div>
          <h2><span className={`led led-${programLed(p)}`} /> {p.name}</h2>
          <p>
            {p.path ?? ""} · {p.status}{run?.stage && p.status === "converting" ? ` · ${run.stage}` : ""}{p.reason ? ` · ${p.reason}` : ""}
            {p.runId && <> · <a href={`#run=${p.runId}`}>Java, diff and trace</a></>}
          </p>
        </div>
      </div>
      <ol className="trace-list dlv-log" ref={log}>
        {!run && <li className="dlv-idle">{p.status === "queued" ? "waiting for its turn…" : "no run recorded"}</li>}
        {run?.events.map((e, i) => (
          <li key={i} className={`dlv-line dlv-ev-${e.type}${e.type === "breaker" && e.broke ? " dlv-broke" : ""}`}>
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

function StartDelivery({ busy, onStarted }: { busy: boolean; onStarted: (id: string) => void }) {
  const config = useApiConfig();
  const open = config?.publicImports?.enabled ?? false;
  const [asAdmin, setAsAdmin] = useState(false);
  const admin = !open || asAdmin;
  const [legacy, setLegacy] = useState("");
  const [target, setTarget] = useState("https://github.com/Nivetha200111/quillmark-java");
  const [parallel, setParallel] = useState(true);
  const [breaker, setBreaker] = useState(true);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [passcode, setPasscode] = useState("");
  const limits = config?.publicImports;
  return (
    <section className="panel dlv-start" id="new-delivery">
      <div className="panel-heading">
        <div>
          <h2>{admin ? "Start a delivery" : "Import a repository"}</h2>
          <p>
            {admin
              ? "Paste the legacy repository and the repository that should receive the pull request."
              : "Paste any public GitHub repository with COBOL. Muse Spark converts each program to Java; Diocle runs both against GnuCOBOL and repairs until they agree."}
          </p>
        </div>
      </div>
      <form
        className="dlv-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          setSending(true);
          try {
            onStarted(await startDelivery(admin ? { legacy, target, parallel, breaker } : { legacy }, admin ? passcode : ""));
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setSending(false);
          }
        }}
      >
        <label>
          <span>Legacy repository (COBOL in)</span>
          <input value={legacy} onChange={(e) => setLegacy(e.target.value)} spellCheck={false}
                 placeholder="https://github.com/<owner>/<repo>" required />
        </label>
        {!admin && (
          <p className="dlv-note">
            Try <button type="button" className="link-button" onClick={() => setLegacy(LINKS.legacy)}>{repoName(LINKS.legacy)}</button>,
            the fictional bank's mainframe export, or your own.
          </p>
        )}
        {admin && (
          <>
            <label>
              <span>Target repository (pull request out)</span>
              <input value={target} onChange={(e) => setTarget(e.target.value)} spellCheck={false} />
            </label>
            {config?.startNeedsPasscode && (
              <label>
                <span>Admin passcode</span>
                <input type="password" value={passcode} onChange={(e) => setPasscode(e.target.value)} autoComplete="current-password" />
              </label>
            )}
          </>
        )}
        <div className="dlv-form-row">
          {admin && (
            <>
              <label className="dlv-check"><input type="checkbox" checked={parallel} onChange={(e) => setParallel(e.target.checked)} /> Swarm: convert programs in parallel</label>
              <label className="dlv-check"><input type="checkbox" checked={breaker} onChange={(e) => setBreaker(e.target.checked)} /> Breaker: attack each certified program</label>
            </>
          )}
          <button className="button primary" type="submit" disabled={busy || sending || (!admin && limits?.budgetLeft === false)}>
            {busy ? "A job is running" : sending ? "Starting…" : admin ? "Start delivery" : "Import and convert"}
          </button>
        </div>
        {admin ? (
          <p className="dlv-note">
            Uses Meta Muse Spark within the caps in <span className="mono">.env</span> (calls per run, programs per delivery, parallel agents).
            Only allowed GitHub owners; one delivery at a time.
            {open && <> <button type="button" className="link-button" onClick={() => setAsAdmin(false)}>Back to import</button></>}
          </p>
        ) : (
          <p className="dlv-note">
            Up to {limits?.maxPrograms} programs of {limits?.maxLines?.toLocaleString()} lines each, one job at a time.
            Imported code is compiled and run in an isolated sandbox with no network and no credentials.
            Results stay here; nothing is pushed to your repository.
            {limits && !limits.budgetLeft && <strong> The conversion budget for the last 24 hours is used up; try again later.</strong>}
            {" "}<button type="button" className="link-button" onClick={() => setAsAdmin(true)}>Deliver as a pull request (passcode)</button>
          </p>
        )}
        {error && <p className="dlv-error">{error}</p>}
      </form>
    </section>
  );
}

export default function DeliveryView() {
  const [list, setList] = useState<DeliveryListItem[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(() => Date.now());

  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const load = () => fetchDeliveries().then((items) => {
      setList(items);
      setSelected((current) => current ?? items[0]?.id ?? null);
    }).catch(() => setError("unreachable"));
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [refresh]);
  const started = (id: string) => {
    setSelected(id);
    setDelivery(null);
    setRefresh((n) => n + 1);
  };
  const anyRunning = (list ?? []).some((d) => !["done", "failed"].includes(d.stage));

  useEffect(() => {
    if (!selected) return;
    let stop = false;
    const tick = async () => {
      try {
        const d = await fetchDelivery(selected);
        if (!stop) setDelivery(d);
      } catch (e) {
        const message = (e as Error).message;
        if (!stop && !message.includes("HTTP 404")) setError(message);  // a just-started delivery appears within seconds
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
  if (list === null) return <><Skeleton rows={3} label="Loading deliveries" /><Skeleton rows={5} label="Loading delivery" /></>;
  const form = <StartDelivery busy={anyRunning} onStarted={started} />;
  if (list.length === 0) return form;
  if (!delivery) return <>{form}<Skeleton rows={5} label="Loading delivery" /></>;

  const running = !["done", "failed"].includes(delivery.stage);
  return (
    <>
      {form}
      <section className="panel runs-header dlv-header">
        <div>
          <div className="runs-badges">
            <span className={`badge ${running ? "badge-amber" : delivery.stage === "done" ? "badge-green" : "badge-amber"}`}>
              {running ? "● LIVE" : delivery.stage === "failed" ? "Failed" : delivery.target ? "Delivered" : "Done"}
            </span>
            {delivery.public && <span className="badge">Visitor import</span>}

            {list.length > 1 && (
              <select className="dlv-select" value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
                {list.map((d) => <option key={d.id} value={d.id}>{d.id} · {d.stage}{d.target ? "" : " · visitor import"}</option>)}
              </select>
            )}
          </div>
          <h2>
            <a href={delivery.legacy.repository} target="_blank" rel="noreferrer">{repoName(delivery.legacy.repository)}</a>
            {"  →  "}
            {delivery.target
              ? <a href={delivery.target} target="_blank" rel="noreferrer">{repoName(delivery.target)}</a>
              : "verified Java"}
          </h2>
          <p>
            {delivery.target ? "COBOL in, certified Java out as a pull request." : "COBOL in, Java verified against the original out."} Elapsed <span className="mono">{elapsed(delivery.startedAt, delivery.finishedAt, now)}</span>
            {delivery.error && delivery.stage !== "failed" ? ` · error: ${delivery.error}` : ""}
          </p>
          {failureReason(delivery, list) && <p className="dlv-reason">{failureReason(delivery, list)}</p>}
          <p className="dlv-canonical">
            The delivery we cite as evidence is <a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a>:
            it re-delivers INTACCR, and that repository&apos;s CI re-verifies all six programs under one pinned verifier.
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
              <p>Opened on {repoName(delivery.target ?? "")}. CI re-runs the proof on fresh inputs Diocle never saw.</p>
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
