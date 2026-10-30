"use client";

// Mission control: a replay of a recorded run, built only from the data stored with it (see lib/mission.ts).
// It is not live and calls no model.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Brand } from "./ui";
import { ASSURANCE_BADGE, fetchRun, fetchRuns, hostOf, type Run, type RunListItem } from "@/lib/runs";

// "certified" only for a plain certified run; a convert-anyway label is shown as itself, never as certified.
const statusWord = (run: Run) => run.certified ? "certified" : run.assurance ? ASSURANCE_BADGE[run.assurance].label.toLowerCase() : "not certified";
import { AGENTS, tierLabel, buildSteps, castStats, hasTeamData, priceOf, totalsAt, type AgentKey } from "@/lib/mission";

const DEFAULT_RUN = "interest-accrual-20261029-230750";
const SPEEDS = [0.5, 1, 2, 4, 8];

const usd = (n: number) => `$${n.toFixed(n < 1 ? 4 : 2)}`;
const num = (n: number) => n.toLocaleString("en-US");
const when = (s: string | null) => (s ? s.replace("T", " ") : "date not recorded");

export default function MissionControl() {
  const [list, setList] = useState<RunListItem[] | null>(null);
  const [runs, setRuns] = useState<Record<string, Run>>({});
  const [failed, setFailed] = useState(false);
  const [runId, setRunId] = useState(DEFAULT_RUN);

  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("run");
    if (wanted) setRunId(wanted);
    fetchRuns()
      .then(async (items) => {
        setList(items);
        // Only runs that recorded a team (breaker, cross-check or tiers) are offered. Run files are small; fetch them all.
        const got = await Promise.allSettled(items.map((i) => fetchRun(i.id)));
        const ok: Record<string, Run> = {};
        for (const g of got) if (g.status === "fulfilled" && hasTeamData(g.value)) ok[g.value.id] = g.value;
        setRuns(ok);
      })
      .catch(() => setFailed(true));
  }, []);

  const options = useMemo(
    () => (list ?? []).filter((i) => runs[i.id]).sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? "")),
    [list, runs],
  );
  const loaded = Object.keys(runs).length > 0;
  const run = runs[runId] ?? (loaded && options.length ? runs[options[0].id] : undefined);
  const notFound = loaded && !!run && run.id !== runId ? runId : null;

  return (
    <div className="mc-page">
      <header className="mc-top">
        <a href="/" aria-label="Diocle home"><Brand /></a>
        <nav aria-label="Main navigation" className="mc-nav">
          <a href="/">Home</a>
          <a href="/runs">Live runs</a>
          <a href="/evidence">Evidence</a>
          <a href="/mission" aria-current="page">Mission control</a>
          <a href="/bugs">Bug of the day</a>
        </nav>
      </header>
      <main className="mc-main">
        <h1>Mission control</h1>
        <p className="mc-lede">
          The agents of one recorded run, working as a team. Only the verifier (GnuCOBOL against the Java, on the same inputs)
          can certify anything; the models propose.
        </p>
        {failed && (
          <section className="panel mc-empty" role="alert">
            <h2>The engine could not be reached</h2>
            <p>Mission control replays runs stored on the Diocle engine and has nothing to show without them. No sample is faked in its place. Try again later, or read the recorded runs in the repository docs.</p>
          </section>
        )}
        {!failed && !list && <p className="mc-note" role="status">Loading recorded runs…</p>}
        {!failed && list && !run && Object.keys(runs).length === 0 && <p className="mc-note" role="status">Loading run details…</p>}
        {!failed && list && Object.keys(runs).length > 0 && !run && (
          <section className="panel mc-empty"><h2>No run to replay</h2><p>None of the stored runs recorded a breaker, cross-check or tier data.</p></section>
        )}
        {notFound && <p className="mc-note mc-notfound" role="status">Run <code>{notFound}</code> was not found (or has no breaker, cross-check or tier data), so the newest run that has is shown.</p>}
        {run && <Replay key={run.id} run={run} options={options} pick={(id) => { setRunId(id); window.history.replaceState(null, "", `?run=${encodeURIComponent(id)}`); }} />}
      </main>
    </div>
  );
}

function Replay({ run, options, pick }: { run: Run; options: RunListItem[]; pick: (id: string) => void }) {
  const steps = useMemo(() => buildSteps(run), [run]);
  const stats = useMemo(() => castStats(run), [run]);
  const N = steps.length;
  // Replay only mounts on the client after the run has loaded, so matchMedia is safe to read here and there is no flash.
  const [reduced, setReduced] = useState(() => window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [at, setAt] = useState(() => (reduced || N === 0 ? N : 0));  // steps shown; N = the final state
  const [playing, setPlaying] = useState(() => !reduced && N > 0);
  const [speed, setSpeed] = useState(2);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => { setReduced(mq.matches); if (mq.matches) { setPlaying(false); setAt(N); } };
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [N]);

  useEffect(() => {
    if (!playing) return;
    if (at >= N) { setPlaying(false); return; }
    const t = setTimeout(() => setAt((a) => a + 1), (at === 0 ? 500 : steps[at - 1].ms) / speed);
    return () => clearTimeout(t);
  }, [playing, at, N, speed, steps]);

  const toggle = useCallback(() => {
    if (!playing && at >= N) setAt(0);
    setPlaying((p) => !p);
  }, [playing, at, N]);

  const shown = steps.slice(0, at);
  const cur = shown[shown.length - 1];
  const totals = totalsAt(steps, at);
  const spent = Object.values(totals).reduce((n, t) => n + t.usd, 0);
  const tokens = Object.values(totals).reduce((n, t) => n + t.tokens, 0);
  const finalUsd = run.usage.estimatedCostUsd;
  const done = at >= N;
  const tierNow = shown.reduce((t, s) => (s.tierUp ? s.tierUp.index : t), 0);
  const cx = [...shown].reverse().find((s) => s.counterexample !== undefined)?.counterexample;
  const patch = [...shown].reverse().find((s) => s.patch)?.patch;
  const certs = shown.filter((s) => s.cert);
  const lastCert = certs[certs.length - 1];
  const final = run.after;
  const log = useRef<HTMLOListElement>(null);
  useEffect(() => { const el = log.current; if (el && !reduced) el.scrollTop = el.scrollHeight; }, [at, reduced]);

  const tiers = run.tiers;
  return (
    <>
      <section className="mc-banner" aria-label="About this replay">
        <strong>Replay of a recorded run</strong>
        <span>
          Run <code>{run.id}</code>, recorded {when(run.createdAt)} · {run.program} · {statusWord(run)}.
          Nothing here is live: it steps through the events and model calls stored with the run, in their recorded order
          (run events carry no timestamps, so pauses are not real durations).
        </span>
        <label className="mc-pick">
          <span>Run</span>
          <select value={run.id} onChange={(e) => pick(e.target.value)}>
            {options.map((o) => <option key={o.id} value={o.id}>{o.id}{o.certified ? "" : o.assurance ? ` (${ASSURANCE_BADGE[o.assurance].label.toLowerCase()})` : " (not certified)"}</option>)}
          </select>
        </label>
      </section>

      <section aria-label="The team" className="mc-cast">
        {AGENTS.map((a) => {
          const k = a.key as AgentKey;
          const st = stats[k];
          const live = totals[k];
          const active = !done && cur?.agent === k;
          const verifier = k === "verifier";
          const guardInfo = k === "guard" ? run.guard : null;
          const model = verifier ? null : k === "crosscheck" ? (st?.models[0] ?? run.crosscheck?.model ?? null)
            : k === "guard" ? (guardInfo?.review ? (st?.models[0] ?? guardInfo.review.model) : null) : st?.models[0] ?? null;
          const used = verifier || !!st || (k === "guard" && !!guardInfo) || (k === "crosscheck" && !!run.crosscheck);
          return (
            <article key={k} className={`mc-agent${active ? " is-active" : ""}${used ? "" : " is-idle"}${verifier ? " is-verifier" : ""}`} aria-current={active ? "true" : undefined}>
              <h3>{a.name}</h3>
              <p className="mc-job">{a.job}</p>
              {verifier ? (
                <>
                  <p className="mc-model">no model: GnuCOBOL + the Java</p>
                  <p className="mc-only">The only agent that certifies.</p>
                </>
              ) : used ? (
                <>
                  <p className="mc-model" title={model ?? ""}>{model ?? (k === "guard" ? "policy checks, no model call" : "no model call logged")}</p>
                  {model && <p className="mc-host">{hostOf(model)}</p>}
                  <p className="mc-nums">{num(live.tokens)} tokens · {usd(live.usd)}{st ? <small> of {num(st.tokens)} · {usd(st.usd)}</small> : null}</p>
                </>
              ) : <p className="mc-model">not used in this run</p>}
            </article>
          );
        })}
      </section>

      <div className="mc-grid">
        <section className="panel mc-meter" aria-label="Cost and tiers">
          <div className="panel-heading"><div><h2>Cost meter</h2><p>Priced from the logged model calls. Each step&apos;s cost is assigned in call order within its role, so where it lands on the timeline is approximate.</p></div></div>
          <div className="mc-body">
            <div className="mc-cost">
              <span className="mc-cost-n">{usd(spent)}</span>
              <span className="mc-cost-of">of {finalUsd === null ? "an unrecorded total" : usd(finalUsd)} · {num(tokens)} tokens · {num(run.usage.calls)} model calls in total</span>
              {finalUsd !== null && <span className="mc-cost-of">unattributed: {usd(Math.max(0, finalUsd - spent))}{finalUsd - spent > 0.00005 ? (done ? " (cost the replay could not place on a step)" : " (cost not yet reached by the replay)") : ""}</span>}
              <div className="mc-bar" aria-hidden="true"><i style={{ width: `${finalUsd ? Math.min(100, (spent / finalUsd) * 100) : 0}%` }} /></div>
            </div>
            {tiers?.enabled ? (
              <>
                <h3 className="mc-sub">Model tiers for the repair agent</h3>
                <ol className="mc-tiers">
                  {tiers.configured.map((m, i) => {
                    const p = priceOf(m);
                    return (
                      <li key={m} className={i === tierNow ? "is-on" : i < tierNow ? "was-on" : ""}>
                        <strong>Tier {i + 1}: {tierLabel(m)}</strong> <code>{m}</code>
                        <small>{p ? `$${p[0]} in · $${p[1]} cached · $${p[2]} out, per million tokens${m.includes("wonder") ? " (per third-party coverage, unconfirmed)" : ""}` : "price not on file"}</small>
                        {i === tierNow && <b> (working now)</b>}
                      </li>
                    );
                  })}
                </ol>
                <p className="mc-note">
                  {tiers.escalations.length ? `${tiers.escalations.length} escalation(s) recorded.` : "No escalation happened in this run: the repair agent stayed on the first tier."}
                  {tiers.breakerModel ? ` The breaker used ${tiers.breakerModel}.` : ""}
                  {tiers.capCalls !== undefined ? ` Tier spend cap: ${tiers.capCalls} calls or ${usd(tiers.capUsd ?? 0)}; used ${tiers.escalatedCalls ?? 0} calls, ${usd(tiers.escalatedUsd ?? 0)}.` : ""}
                </p>
              </>
            ) : <p className="mc-note">Tiers were not enabled in this run.</p>}
          </div>
        </section>

        <section className="panel mc-stage" aria-label="Breaker input and repair patch">
          <div className="panel-heading"><div><h2>Breaker input and repair patch</h2><p>What the breaker found, and the latest patch the repair agent applied.</p></div></div>
          <div className="mc-body mc-split">
            <div>
              <h3 className="mc-sub">Failing input</h3>
              {cx !== undefined && run.breaker?.counterexamples.length ? (
                run.breaker.counterexamples.slice(0, cx + 1).map((c, i) => (
                  <div key={i}>
                    <pre className="mc-code" tabIndex={0}>{c.input}</pre>
                    <p className="mc-why">{c.why}</p>
                    <p className="mc-diff"><code>{c.diff}</code></p>
                  </div>
                ))
              ) : <p className="mc-note">{run.breaker?.broke ? "Appears when the breaker breaks the Java." : "The breaker did not break this run's Java, or did not run."}</p>}
            </div>
            <div>
              <h3 className="mc-sub">Latest repair patch</h3>
              {patch ? (
                <>
                  <p className="mc-why">{patch.rationale}</p>
                  <pre className="mc-code" tabIndex={0}>{`// ${patch.path}  (stored excerpt)\n${patch.text}`}</pre>
                </>
              ) : <p className="mc-note">{steps.some((s) => s.patch) ? "Appears when the repair agent patches the Java." : "The repair agent applied no patch in this run."}</p>}
            </div>
          </div>
        </section>
      </div>

      <section className={`panel mc-cert${lastCert?.cert?.passed && done ? " is-green" : ""}`} aria-label="Held-out certification">
        <div className="panel-heading"><div><h2>Held-out certification</h2><p>Run by the verifier. The certification inputs are fresh for each round and the repair agent is not shown them in that round, but failures from an earlier round can feed a later repair.</p></div></div>
        <div className="mc-body">
          {lastCert ? (
            <p className="mc-cert-line" role="status">
              <span className={`mc-light ${lastCert.cert!.passed ? "ok" : "bad"}`} aria-hidden="true" />
              {lastCert.cert!.result}
              {done && final ? <strong> Final: {num(final.passed)} of {num(final.total)} inputs match, stdout {final.stdoutMatch ? "matches" : "differs"}; {statusWord(run)}. {run.assurance === "certified-against-repaired-cobol" ? "Compared against the PATCHED COBOL, not the original; a person must confirm the patch." : "Certified on the inputs tried; not a proof of equivalence."}</strong> : null}
            </p>
          ) : <p className="mc-note">Not yet reached in the replay.</p>}
          {certs.length > 1 && <p className="mc-note">{certs.length} certification rounds so far; the last one counts.</p>}
        </div>
      </section>

      <section className="panel mc-timeline" aria-label="Replay timeline">
        <div className="panel-heading">
          <div><h2>Timeline</h2><p>{N ? `Step ${at} of ${N}. ${cur ? cur.title : "Press play to start."}` : "This run stored no events to replay."}</p></div>
        </div>
        <div className="mc-body">
          {N > 0 && (
            <div className="mc-controls">
              <button type="button" className="button primary" onClick={toggle}>{playing ? "Pause" : done ? "Replay" : "Play"}</button>
              <label className="mc-scrub">
                <span className="sr-only">Scrub through the recorded steps</span>
                <input type="range" min={0} max={N} value={at} onChange={(e) => { setPlaying(false); setAt(Number(e.target.value)); }} aria-valuetext={`Step ${at} of ${N}`} />
              </label>
              <div role="group" aria-label="Playback speed" className="mc-speed">
                {SPEEDS.map((s) => <button key={s} type="button" aria-pressed={speed === s} className={speed === s ? "on" : ""} onClick={() => setSpeed(s)}>{s}x</button>)}
              </div>
            </div>
          )}
          <ol className="mc-log" ref={log} tabIndex={0} aria-label="Recorded steps up to the playhead">
            {shown.map((s) => (
              <li key={s.id} className={`mc-ev mc-ev-${s.kind}${s === cur && !done ? " is-now" : ""}${s.kind === "breaker" ? (s.counterexample !== undefined ? " fail" : " pass") : ""}${s.cert ? (s.cert.passed ? " pass" : " fail") : ""}`}>
                <span className="mc-tag">{AGENTS.find((a) => a.key === s.agent)?.name ?? "Engine"}</span>
                <span className="mc-ev-main"><strong>{s.title}</strong>{s.detail ? <> <span>{s.detail}</span></> : null}</span>
                {s.delta && <span className="mc-ev-cost">{usd(s.delta.usd)}</span>}
              </li>
            ))}
            {!shown.length && N > 0 && <li className="mc-note">Waiting for the first step…</li>}
          </ol>
        </div>
      </section>
    </>
  );
}
