"use client";

// "Current run": one place that shows whatever the engine is doing right now (a repository import or delivery, a live
// Convert / Printout press, or a voice question), read from the engine's own records every few seconds. Nothing here is
// a replay or a mock: when nothing runs, the page says so and points to the three ways to start something.
import { useEffect, useState } from "react";
import { fetchSamplesStatus, fetchJob, type LiveJob } from "@/lib/live";
import { fetchAsk, type AskJob } from "@/lib/ask";
import { fetchDelivery, fetchDeliveries, type Delivery, type DeliveryListItem } from "@/lib/deliveries";

type Busy = { kind: "delivery"; d: Delivery } | { kind: "live"; j: LiveJob } | { kind: "ask"; j: AskJob };


function elapsed(start: string, end: string | null, now: number) {
  const ms = Math.max(0, (end ? Date.parse(end) : now) - Date.parse(start));
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

const repoName = (url: string) => url.replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "");

function Led({ state }: { state: "ok" | "bad" | "busy" | "off" }) {
  return <span className={`led led-${state}`} aria-hidden="true" />;
}

function DeliveryNow({ d, now }: { d: Delivery; now: number }) {
  const certified = d.programs.filter((p) => p.status === "certified").length;
  const total = d.programs.filter((p) => p.status !== "skipped").length; // as on the Delivery page: skipped programs are listed, not counted
  const steps: { label: string; state: "ok" | "bad" | "busy" | "off"; note: string }[] = [
    { label: "1. Clone & analyze", state: d.stage === "analyzing" ? "busy" : total ? "ok" : d.stage === "failed" ? "bad" : "off",
      note: d.stage === "analyzing" ? "reading programs and copybooks" : `${total} program${total === 1 ? "" : "s"}` },
    { label: "2. Convert & certify", state: d.stage === "converting" ? "busy" : ["delivering", "done"].includes(d.stage) ? "ok" : d.stage === "failed" ? "bad" : "off",
      note: total ? `${certified}/${total} certified` : "waiting for the program list" },
    ...(d.target ? [{ label: "3. Open pull request", state: (d.pullRequest ? "ok" : d.stage === "delivering" ? "busy" : "off") as "ok" | "busy" | "off",
      note: d.pullRequest ? "opened" : "waiting" }] : []),
  ];
  return (
    <section className="panel now-panel">
      <div className="panel-heading">
        <div>
          <h2>{d.target ? "Delivering a repository" : "Importing a repository"}</h2>
          <p>
            <a href={d.legacy.repository} target="_blank" rel="noreferrer">{repoName(d.legacy.repository)}</a>
            {" → "}{d.target ? <a href={d.target} target="_blank" rel="noreferrer">{repoName(d.target)}</a> : "verified Java (results stay on this site)"}
            {" · "}running for <span className="mono">{elapsed(d.startedAt, d.finishedAt, now)}</span>
          </p>
        </div>
      </div>
      <div className="now-steps">
        {steps.map((s) => (
          <div key={s.label} className={`now-step now-${s.state}`}><Led state={s.state} /><div><strong>{s.label}</strong><span>{s.note}</span></div></div>
        ))}
      </div>
      {total > 0 && (
        <table className="now-table">
          <thead><tr><th>Program</th><th>Status</th><th>Run</th></tr></thead>
          <tbody>
            {d.programs.map((p) => (
              <tr key={p.name}>
                <td className="mono">{p.name}</td>
                <td><Led state={p.status === "certified" ? "ok" : p.status === "converting" ? "busy" : p.status === "not-certified" ? "bad" : "off"} /> {p.status}{p.reason ? <span className="now-reason"> · {p.reason}</span> : null}</td>
                <td>{p.runId ? <a href={`/runs#run=${encodeURIComponent(p.runId)}`}>open the run</a> : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="now-more"><a href="/delivery">Full detail on the Delivery page</a></p>
    </section>
  );
}

function EventsNow({ title, sub, stage, started, finished, events, href, linkText, now }: {
  title: string; sub: string; stage: string; started: string; finished: string | null; events: { at: string; message: string }[];
  href: string; linkText: string; now: number;
}) {
  return (
    <section className="panel now-panel">
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          <p>{sub} · stage <span className="mono">{stage}</span> · running for <span className="mono">{elapsed(started, finished, now)}</span></p>
        </div>
      </div>
      <ol className="now-events">
        {events.slice(-12).map((e, i) => <li key={i}>{e.message}</li>)}
        {events.length === 0 && <li>Starting…</li>}
      </ol>
      <p className="now-more"><a href={href}>{linkText}</a></p>
    </section>
  );
}

export default function NowView() {
  const [busy, setBusy] = useState<Busy | null>(null);
  const [idle, setIdle] = useState(false);
  const [off, setOff] = useState(false); // the engine's live status is switched off (DIOCLE_PUBLIC_SAMPLES=0): busy is not reported then
  const [error, setError] = useState(false);
  const [last, setLast] = useState<DeliveryListItem | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // One request at a time (no overlapping ticks); every 3 s while something runs, every 10 s when idle; paused in a hidden tab.
    const loop = async () => {
      let running = false;
      if (!document.hidden) {
        try {
          const status = await fetchSamplesStatus();
          if (status && status.enabled === false) {
            if (!stop) { setOff(true); setBusy(null); setIdle(false); setError(false); }
          } else {
            const id = status?.busy ?? null;
            let next: Busy | null = null;
            if (id?.startsWith("delivery-")) next = { kind: "delivery", d: await fetchDelivery(id) };
            else if (id?.startsWith("ask-")) next = { kind: "ask", j: await fetchAsk(id) };
            else if (id) next = { kind: "live", j: await fetchJob(id) };
            running = !!next;
            if (!stop) { setOff(false); setBusy(next); setIdle(!next); setError(false); }
            if (!next) {
              const list = await fetchDeliveries().catch(() => [] as DeliveryListItem[]);
              if (!stop) setLast(list.find((d) => d.stage === "done" && d.pullRequest) ?? list.find((d) => d.stage === "done") ?? null);
            }
          }
        } catch {
          if (!stop) { setError(true); setBusy(null); setIdle(false); }
        }
      }
      if (!stop) timer = setTimeout(loop, running ? 3000 : 10000);
    };
    const wake = () => { if (!document.hidden) { clearTimeout(timer); loop(); } };
    loop();
    document.addEventListener("visibilitychange", wake);
    const c = setInterval(() => setNow(Date.now()), 1000);
    return () => { stop = true; clearTimeout(timer); clearInterval(c); document.removeEventListener("visibilitychange", wake); };
  }, []);

  return (
    <div className="now-view">
      {busy && (
        <p className="now-banner"><span className="now-live-dot" aria-hidden="true" /> <strong>Running now.</strong> Read from the engine&apos;s own records every few seconds; the engine runs one job at a time.</p>
      )}

      {error && <p className="dlv-reason">The engine could not be reached just now; this page keeps trying.</p>}
      {off && <p className="dlv-reason">Live status is switched off on this engine right now, so this page cannot tell whether something is running. The Delivery page still lists every delivery.</p>}

      {busy?.kind === "delivery" && <DeliveryNow d={busy.d} now={now} />}
      {busy?.kind === "live" && (
        <EventsNow title={busy.j.sample === "addfee" ? "Converting a sample (ADDFEE)" : "Reading a printout"}
          sub={busy.j.sample === "addfee" ? "Muse Spark translates, GnuCOBOL checks" : "Muse Wonder reads the picture, GnuCOBOL checks"}
          stage={busy.j.stage} started={busy.j.startedAt} finished={busy.j.finishedAt} events={busy.j.events}
          href="/try#live" linkText="Try the live buttons yourself (that page follows only jobs started in your own browser)" now={now} />
      )}
      {busy?.kind === "ask" && (
        <EventsNow title="Answering a spoken question" sub="Muse Voice Transcribe, then Muse Spark claims, then GnuCOBOL verdicts"
          stage={busy.j.stage} started={busy.j.startedAt} finished={busy.j.finishedAt} events={busy.j.events}
          href="/try#ask" linkText="Ask a question yourself (that page follows only questions asked in your own browser)" now={now} />
      )}

      {idle && (
        <>
          <section className="panel now-panel">
            <div className="panel-heading"><div><h2>Nothing is running right now</h2><p>Start something; it shows up here while it runs.</p></div></div>
            <div className="now-starts">
              <a className="now-start" href="/try"><strong>Try it in one click</strong><span>Convert a sample, read a printout, or ask a program a question out loud.</span></a>
              <a className="now-start" href="/delivery"><strong>Import a COBOL repository</strong><span>Paste a public GitHub link; Diocle converts and certifies each program it can.</span></a>
              <a className="now-start" href="/evidence"><strong>See the evidence</strong><span>Every run, every cost, every refusal, with links to check each claim.</span></a>
            </div>
          </section>
          {last && (
            <section className="panel now-panel">
              <div className="panel-heading"><div><h2>{last.pullRequest ? "Last delivered pull request" : "Last finished delivery"}</h2><p>Finished; not running now. Every delivery, including visitor imports, is on the Delivery page.</p></div></div>
              <p className="now-last">
                <Led state={last.pullRequest ? "ok" : "off"} /> <a href={last.legacy.repository} target="_blank" rel="noreferrer">{repoName(last.legacy.repository)}</a>
                {last.target ? <> → <a href={last.target} target="_blank" rel="noreferrer">{repoName(last.target)}</a></> : " → verified Java"}
                {" · "}{last.programs} program{last.programs === 1 ? "" : "s"}
                {last.pullRequest && <> · <a href={last.pullRequest} target="_blank" rel="noreferrer">pull request</a></>}
                {" · "}<a href="/delivery">open on the Delivery page</a>
              </p>
            </section>
          )}
        </>
      )}
      {!busy && !idle && !error && !off && <p className="live-caps">Checking the engine…</p>}
    </div>
  );
}
