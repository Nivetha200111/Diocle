"use client";

// The two public live buttons on the Try it live page (/try). Nothing here is replayed or invented: every line shown comes from the job
// record or the run record the engine returns while the work happens. The buttons send a sample name and nothing else; an image goes through its own capped route.
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "./ui";
import { ASSURANCE_BADGE, fetchRun, type Run } from "@/lib/runs";
import type { ButtonStatus, SamplesStatus, UploadStatus } from "@/lib/config";
import { fetchJob, fetchSamplesStatus, printoutImageUrl, shrinkImage, startLive, startLiveUpload, viewKey, type LiveJob, type LiveSample, type PrintoutResult } from "@/lib/live";

const usd = (n: number | null | undefined) => (n === null || n === undefined ? "n/a" : `$${n.toFixed(n < 1 ? 4 : 2)}`);
const cap = (n: number) => `$${n.toFixed(2)}`;
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
    let inflight = false;
    const tick = async () => {
      const id = watch;
      if (!id || stop || inflight) return;
      inflight = true;
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
      inflight = false;
      if (again && !stop) timer = setTimeout(tick, delay);
    };
    timer = setTimeout(tick, 100);
    // A hidden or covered tab has its timers throttled; when it comes back, check the job now instead of waiting.
    const onVisible = () => {
      if (document.visibilityState !== "visible" || stop || !watch || inflight) return;
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
          <p>Free, with no model: Try the sample on the <a href="/">home page</a>.</p>
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
          what="Muse Spark translates the small COBOL program ADDFEE to Java, then both run on the same generated inputs."
        />
        <Card
          title="Read a printout"
          sample="loyalty-waiver-printout"
          label="Read the printout now"
          b={s?.printout}
          reason={reasonOf(s?.printout)}
          onStart={start}
          what="Muse Wonder reads this listing and writes the COBOL; the comparison with the original decides."
          image
        />
      </div>
      {s?.upload?.enabled && <ImageUpload status={s.upload} busy={starting || job?.status === "running"} onError={setError}
        onStart={async (file) => {
          setStarting(true); setError(null); setJob(null); setRun(null);
          try { follow(await startLiveUpload(await shrinkImage(file, s.upload?.maxBytes ?? 2097152))); }
          catch (e) { setError(e instanceof Error ? e.message : "The request failed."); refresh(); }
          finally { setStarting(false); }
        }} />}
      <details className="inline-more live-limits" id="live-limits">
        <summary>Limits and privacy</summary>
        <p>
          <strong>Try the sample on the home page is free and calls no model.</strong> The buttons here call a real Meta model, which
          costs money, so each has a small daily limit. Two run on fixed, bundled, synthetic samples and take no input from
          you. A third reads a picture you send: it goes only to the vision model, and what it writes is compiled and run only in
          the sandbox. If a button has reached its limit, the evidence on the home and Evidence pages still works.
          {s && <> Limit for this page: {cap(s.budgetUsd)} a day; {usd(s.spentTodayUsd)} used in the last 24 hours (estimated at list prices).</>}
        </p>
        <h4>Convert a sample now</h4>
        <p>Muse Spark translates the small COBOL program ADDFEE (a fee added to account records) to Java, then GnuCOBOL and the Java run on the same generated inputs in the sandbox and a held-out check is run on fresh ones. A normal run, labelled as a live sample run.</p>
        <Caps sample="addfee" b={s?.convert} unit="conversions" />
        <h4>Read a printout</h4>
        <p>Muse Wonder reads the picture of a COBOL listing below and writes the COBOL. It is compiled and run in the sandbox against the original LOYWAIVE on about a thousand inputs. A model reading a printout certifies nothing: the comparison decides.</p>
        <Caps sample="loyalty-waiver-printout" b={s?.printout} unit="printout reads" />
        {s?.upload?.enabled && (<>
          <h4>Read your own image</h4>
          <p>
            Send a photo or screenshot of a COBOL listing. Muse Wonder writes the COBOL it sees; it is compiled and run in the sandbox against
            the bundled LOYWAIVE program. To see it match, photograph <a href={printoutImageUrl} target="_blank" rel="noreferrer">this listing</a>.
            Any other program will show as different or refused, which says nothing about how well it was read: compare the text yourself.
          </p>
          <p>
            Your browser shrinks the picture and removes its metadata first. It goes to Meta&apos;s vision model; only you can read the result here. The
            image is deleted when the job ends, and the transcription an hour later. Send synthetic or public code only, never your employer&apos;s or a client&apos;s.
          </p>
          <p>At most {cap(s.upload.maxUsd)} per image. Caps: {s.upload.perVisitorPerDay} per visitor per day, {s.upload.perDay} a day overall ({s.upload.usedToday} used in the last 24 hours, {s.upload.visitorLeft} left for you).</p>
        </>)}
      </details>
      {error && <p className="live-error" role="alert">{error}</p>}
      {job && job.sample === "addfee" && <ConvertProgress job={job} run={run} />}
      {job && job.sample === "loyalty-waiver-printout" && (viewKey(job.id) && job.status !== "running" && !job.printout && !job.error
        ? <p className="live-caps" role="status">The result of this image has been removed: results are kept for an hour.</p>
        : <PrintoutProgress job={job} />)}
    </section>
  );
}

function ImageUpload(p: { status: UploadStatus; busy: boolean; onStart: (file: File) => void; onError: (message: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const why = p.busy ? "A live job is running; this comes back when it finishes." : p.status.reason;
  return (
    <div className="live-card live-upload">
      <h3>Read your own image</h3>
      <p className="live-what">Send a photo of a synthetic or public COBOL listing, never your employer&apos;s or a client&apos;s; Muse Wonder writes the COBOL it sees, compared with LOYWAIVE.</p>
      <div className="ask-actions">
        <input ref={input} type="file" accept="image/png,image/jpeg" aria-label="Choose an image of a COBOL listing"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <button type="button" className="button secondary" disabled={why !== null || !file}
          onClick={() => {
            if (!file) { p.onError("Choose an image first."); return; }
            p.onStart(file);
            setFile(null);
            if (input.current) input.current.value = "";
          }}>Read my image</button>
      </div>
      {why && <p className="live-reason" role="status">Disabled: {why}</p>}
    </div>
  );
}

function Card(p: {
  title: string; sample: LiveSample; label: string; b: ButtonStatus | undefined; reason: string | null;
  onStart: (s: LiveSample) => void; what: string; image?: boolean;
}) {
  const id = `live-${p.sample}`;
  const disabled = p.reason !== null;
  return (
    <div className="live-card">
      <h3>{p.title}</h3>
      <p className="live-what">{p.what}</p>
      <button type="button" className="button primary" disabled={disabled} aria-describedby={`${id}-note ${id}-caps`}
        onClick={() => p.onStart(p.sample)}>{p.label}</button>
      {p.reason && <p id={`${id}-note`} className="live-reason" role="status">{p.reason.startsWith("Checking") ? p.reason : `Disabled: ${p.reason}`}</p>}
      {!p.reason && <p id={`${id}-note`} className="sr-only">Ready.</p>}
      {p.image && (
        <a href={printoutImageUrl} target="_blank" rel="noreferrer" title="Open the whole listing">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img className="live-printout" src={printoutImageUrl} width={520}
            alt="A printed fixed-format COBOL listing of the program LOYWAIVE, with a gutter of line numbers on the left" />
        </a>
      )}
    </div>
  );
}

// Inside "Limits and privacy"; each button still names this line through aria-describedby.
function Caps({ sample, b, unit }: { sample: LiveSample; b: ButtonStatus | undefined; unit: string }) {
  return (
    <p id={`live-${sample}-caps`}>
      At most {cap(b?.maxUsd ?? (sample === "addfee" ? 0.05 : 0.1))} per press.{" "}
      {b ? `${b.visitorLeft} left for you now. Limits per 24 hours: ${b.perVisitorPerDay} ${unit} per visitor and ${b.perDay} overall (${b.usedToday} used in the last 24 hours).` : "Loading limits."}
      {" "}One live job runs at a time.
    </p>
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
            {run.after && run.after.total === 0
              ? <>Held-out check: no cases were compared.</>
              : run.after
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
            {viewKey(job.id) && p.status !== "verified-identical" && " This was compared with the bundled LOYWAIVE program, so a different listing cannot match: it says nothing about how well your image was read."}
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
