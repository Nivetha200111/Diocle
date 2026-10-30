"use client";

// The two public live buttons on Mission control. Nothing here is replayed or invented: every line shown comes from the job
// record or the run record the engine returns while the work happens. The visitor sends a sample name and nothing else.
import { useCallback, useEffect, useState } from "react";
import { Badge } from "./ui";
import { ASSURANCE_BADGE, fetchRun, type Run } from "@/lib/runs";
import type { ButtonStatus, SamplesStatus } from "@/lib/config";
import { fetchJob, fetchSamplesStatus, printoutImageUrl, startLive, type LiveJob, type LiveSample, type PrintoutResult } from "@/lib/live";

const usd = (n: number | null | undefined) => (n === null || n === undefined ? "n/a" : `$${n.toFixed(n < 1 ? 4 : 2)}`);
const num = (n: number) => n.toLocaleString("en-US");
const KEY = "diocle-live-job";

const PRINTOUT_VERDICT: Record<PrintoutResult["status"], string> = {
  "verified-identical": "IDENTICAL to the original",
  differs: "DIFFERS from the original",
  "compiled-unchecked": "COMPILES, NOT CHECKED against the original",
  "compile-failed": "DOES NOT COMPILE",
  refused: "REFUSED before it was compiled",
  "no-transcription": "NO TRANSCRIPTION",
};

function remember(id: string | null) {
  try { if (id) sessionStorage.setItem(KEY, id); else sessionStorage.removeItem(KEY); } catch { /* private window: the page works without it */ }
}
function recall(): string | null {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}

export default function LiveSamples() {
  const [status, setStatus] = useState<SamplesStatus | null | "unreachable">(null);
  const [job, setJob] = useState<LiveJob | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [watch, setWatch] = useState<string | null>(null);  // the job being followed

  const refresh = useCallback(() => {
    fetchSamplesStatus().then((s) => setStatus(s ?? "unreachable")).catch(() => setStatus("unreachable"));
  }, []);

  const follow = useCallback((id: string) => {
    setWatch(id);
    remember(id);
    setError(null);
  }, []);

  useEffect(() => {
    refresh();
    const old = recall();
    if (old) follow(old);
  }, [refresh, follow]);

  // Poll the job (and, for a conversion, its run record) every 1.5 s while it runs, once more when it ends.
  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    const tick = async () => {
      const id = watch;
      if (!id || stop) return;
      let again = true;
      let delay = 1500;
      try {
        const j = await fetchJob(id);
        if (stop) return;
        failures = 0;
        setJob(j);
        if (j.runId) {
          const r = await fetchRun(j.runId).catch(() => null);
          if (!stop && r) setRun(r);
        }
        if (j.status !== "running") { again = false; refresh(); }
      } catch {
        failures += 1;
        if (failures >= 8) { again = false; setError("The engine could not be reached; stopped checking. Reload the page to try again."); }
        else if (!stop) { setError("The engine could not be reached just now; trying again."); delay = Math.min(15000, 1500 * 2 ** failures); }
      }
      if (again && !stop) timer = setTimeout(tick, delay);
    };
    timer = setTimeout(tick, 100);
    // A hidden or covered tab has its timers throttled; when it comes back, check the job now instead of waiting.
    const onVisible = () => {
      if (document.visibilityState !== "visible" || stop || !watch) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(tick, 0);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => { stop = true; if (timer) clearTimeout(timer); document.removeEventListener("visibilitychange", onVisible); };
  }, [refresh, watch]);

  const start = async (sample: LiveSample) => {
    setStarting(true);
    setError(null);
    setJob(null);
    setRun(null);
    try {
      follow(await startLive(sample));
    } catch (e) {
      setError(e instanceof Error ? e.message : "The request failed.");
      refresh();
    } finally {
      setStarting(false);
    }
  };

  const running = job?.status === "running";
  const s = status && status !== "unreachable" ? status : null;
  const reasonOf = (b: ButtonStatus | undefined): string | null =>
    status === "unreachable" ? "The engine could not be reached, so there is nothing to run."
      : status === null ? "Checking what this engine allows…"
        : !s ? "This engine does not offer the live buttons."
          : running ? "A live job is running; the buttons come back when it finishes."
            : starting ? "Starting…" : b?.reason ?? null;

  return (
    <section className="panel live" id="live" aria-labelledby="live-h">
      <div className="panel-heading">
        <div>
          <h2 id="live-h">Try it live</h2>
          <p>
            Two buttons that run a REAL Meta model call on one fixed, bundled, synthetic sample and verify the result.
            They take no input from you: you cannot upload anything here, so nothing you type can reach a model, a
            command or the sandbox. Each press is capped in dollars, in presses per visitor and per day, and runs one at a time.
            {s && <> Together the two buttons may spend at most {usd(s.budgetUsd)} a day; {usd(s.spentTodayUsd)} so far in the last 24 hours (estimates at list prices).</>}
          </p>
        </div>
      </div>
      <div className="live-cards">
        <Card
          title="Convert a sample now"
          sample="addfee"
          label="Convert ADDFEE now"
          b={s?.convert}
          reason={reasonOf(s?.convert)}
          onStart={start}
          what="Muse Spark translates the small COBOL program ADDFEE (a fee added to account records) to Java, then GnuCOBOL and the Java run on the same generated inputs in the sandbox and a held-out check is run on fresh ones. A normal run, labelled as a live sample run."
          unit="conversions"
        />
        <Card
          title="Read a printout"
          sample="loyalty-waiver-printout"
          label="Read the printout now"
          b={s?.printout}
          reason={reasonOf(s?.printout)}
          onStart={start}
          what="Muse Wonder reads the picture of a COBOL listing below and writes the COBOL. It is compiled and run in the sandbox against the original LOYWAIVE on about a thousand inputs. A model reading a printout certifies nothing: the comparison decides."
          unit="printout reads"
          image
        />
      </div>
      {error && <p className="live-error" role="alert">{error}</p>}
      {job && job.sample === "addfee" && <ConvertProgress job={job} run={run} />}
      {job && job.sample === "loyalty-waiver-printout" && <PrintoutProgress job={job} />}
    </section>
  );
}

function Card(p: {
  title: string; sample: LiveSample; label: string; b: ButtonStatus | undefined; reason: string | null;
  onStart: (s: LiveSample) => void; what: string; unit: string; image?: boolean;
}) {
  const id = `live-${p.sample}`;
  const disabled = p.reason !== null;
  return (
    <div className="live-card">
      <h3>{p.title}</h3>
      <p className="live-what">{p.what}</p>
      {p.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="live-printout" src={printoutImageUrl} width={520}
          alt="A printed fixed-format COBOL listing of the program LOYWAIVE, with a gutter of line numbers on the left" />
      )}
      <button type="button" className="button primary" disabled={disabled} aria-describedby={`${id}-note ${id}-caps`}
        onClick={() => p.onStart(p.sample)}>▶ {p.label}</button>
      {p.reason && <p id={`${id}-note`} className="live-reason" role="status">Disabled: {p.reason}</p>}
      {!p.reason && <p id={`${id}-note`} className="sr-only">Ready.</p>}
      <p id={`${id}-caps`} className="live-caps">
        Costs at most {usd(p.b?.maxUsd ?? (p.sample === "addfee" ? 0.02 : 0.1))} per press. Caps:{" "}
        {p.b ? `${p.b.perVisitorPerDay} ${p.unit} per visitor per day, ${p.b.perDay} a day overall (${p.b.usedToday} used in the last 24 hours, ${p.b.visitorLeft} left for you)` : "loading"}
        , one live job at a time, shared with visitor imports.
      </p>
    </div>
  );
}

function ConvertProgress({ job, run }: { job: LiveJob; run: Run | null }) {
  const done = run && (run.status === "certified" || run.status === "not-certified");
  const verdict = run ? (run.certified ? "certified" : run.assurance ? ASSURANCE_BADGE[run.assurance].label.toLowerCase() : "not certified") : null;
  const lines: string[] = [
    ...job.events.map((e) => e.message),
    ...(run?.events ?? []).flatMap((e) =>
      e.type === "stage" && e.message ? [`stage ${e.stage}: ${e.message}`]
        : e.type === "certification" ? [`certification: ${e.result ?? (e.passed ? "passed" : "failed")}`]
          : e.type === "budget" && e.message ? [`budget: ${e.message}`] : []),
  ];
  const u = run?.usage;
  const calls = u?.calls ?? 0;
  return (
    <div className="live-run" aria-labelledby="live-run-h">
      <h3 id="live-run-h">
        <Badge tone={job.status === "running" ? "amber" : job.status === "failed" ? "red" : "green"}>
          {job.status === "running" ? "LIVE, running now" : job.status === "failed" ? "STOPPED" : "FINISHED"}
        </Badge>{" "}
        Live sample run <span className="mono">{run?.id ?? job.id}</span>
      </h3>
      <div className="live-cols">
        <div>
          <h4>What the engine reports, as it happens</h4>
          <ol className="live-events">
            {lines.map((l, i) => <li key={i}>{l}</li>)}
            {job.status === "running" && !done && <li className="live-wait">working…</li>}
          </ol>
        </div>
        <div>
          <h4>Model and cost so far</h4>
          <dl className="live-nums" aria-live="polite">
            <div><dt>Model</dt><dd className="mono">{run?.model ?? "named when the first model call returns"}</dd></div>
            <div><dt>Model calls</dt><dd className="mono">{calls}</dd></div>
            <div><dt>Tokens in / out</dt><dd className="mono">{u ? `${num(u.inputTokens)} / ${num(u.outputTokens)}` : "0 / 0"}</dd></div>
            <div><dt>Estimated cost</dt><dd className="mono">{usd(u?.estimatedCostUsd ?? 0)} of {usd(job.maxUsd)} cap</dd></div>
          </dl>
          {job.status === "running" && calls <= 1 && (
            <p className="live-caps">This program usually needs one model call, so these numbers jump once, when the call returns, rather than climbing.</p>
          )}
        </div>
      </div>
      {job.status === "failed" && <p className="live-error" role="alert">The job stopped: {job.error}. Nothing is claimed about this program.</p>}
      {done && run && (
        <div className="live-result" role="status">
          <p>
            <Badge tone={run.certified ? "green" : "amber"}>{verdict?.toUpperCase()}</Badge>{" "}
            {run.after
              ? <>Held-out check: <strong>{num(run.after.passed)}/{num(run.after.total)}</strong> inputs match GnuCOBOL, stdout {run.after.stdoutMatch ? "matches" : "differs"}.</>
              : <>No held-out result was recorded.</>}{" "}
            {run.certified ? "Certified means the Java matched the original on those inputs, not that it is correct on every input." : run.error ?? ""}
          </p>
          <p>
            <a className="button secondary" href={`/runs#run=${encodeURIComponent(run.id)}`}>Open the run: model card, cost, source and Re-verify</a>
          </p>
        </div>
      )}
    </div>
  );
}

function PrintoutProgress({ job }: { job: LiveJob }) {
  const p = job.printout;
  const d = p?.differential;
  return (
    <div className="live-run" aria-labelledby="live-run-h">
      <h3 id="live-run-h">
        <Badge tone={job.status === "running" ? "amber" : job.status === "failed" ? "red" : "green"}>
          {job.status === "running" ? "LIVE, running now" : job.status === "failed" ? "STOPPED" : "FINISHED"}
        </Badge>{" "}
        Live printout read <span className="mono">{job.id}</span>
      </h3>
      <div className="live-cols">
        <div>
          <h4>What the engine reports, as it happens</h4>
          <ol className="live-events">
            {job.events.map((e, i) => <li key={i}>{e.message}</li>)}
            {job.status === "running" && <li className="live-wait">working…</li>}
          </ol>
        </div>
        <div>
          <h4>Model and cost</h4>
          <dl className="live-nums" aria-live="polite">
            <div><dt>Model</dt><dd className="mono">{p?.model ?? "named when the result is in"}</dd></div>
            <div><dt>Model calls</dt><dd className="mono">{p?.usage.calls ?? "…"}</dd></div>
            <div><dt>Tokens in / out</dt><dd className="mono">{p ? `${num(p.usage.inputTokens)} / ${num(p.usage.outputTokens)}` : "shown when the result is in"}</dd></div>
            <div><dt>Estimated cost</dt><dd className="mono">{p ? usd(p.usage.estimatedCostUsd) : "…"} of {usd(job.maxUsd)} cap</dd></div>
          </dl>
        </div>
      </div>
      {job.status === "failed" && <p className="live-error" role="alert">The job stopped: {job.error}. Nothing is claimed about this printout.</p>}
      {p && (
        <div className="live-result" role="status">
          <p>
            <Badge tone={p.status === "verified-identical" ? "green" : "amber"}>{PRINTOUT_VERDICT[p.status]}</Badge>{" "}
            {d?.ran
              ? <>The transcribed COBOL and the original LOYWAIVE were run in the sandbox on the same inputs: <strong>{num(d.matched)}/{num(d.inputs)}</strong> match
                {d.stdoutMatch !== undefined && <>, stdout {d.stdoutMatch ? "matches" : "differs"}, exit code {d.exitCodeMatch ? "matches" : "differs"}</>}.</>
              : <>The comparison did not run{p.reason ? `: ${p.reason}` : ""}.</>}{" "}
            {p.status === "verified-identical" && "Identical on those inputs is not a proof for every input."}
            {p.status !== "verified-identical" && p.reason && d?.ran ? p.reason : ""}
          </p>
          {p.source ? (<>
            <h4>The COBOL the model transcribed{p.program ? ` (${p.program})` : ""}</h4>
            <pre className="live-source" tabIndex={0} aria-label="Transcribed COBOL source">{p.source}</pre>
          </>) : <p className="live-caps">The model produced no COBOL to show.</p>}
        </div>
      )}
    </div>
  );
}
