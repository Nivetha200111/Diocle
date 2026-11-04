"use client";

// "Ask the original program": a spoken question, transcribed by Muse Voice Transcribe, turned into checkable claims by a Muse
// Spark model, and CHECKED by running the original COBOL under GnuCOBOL. Every stage below is drawn from the job record the
// engine writes while the work happens. The answer is assembled by the engine from confirmed claims only. All text from the
// engine (the heard question, claim statements, values) is rendered as plain text by React, never as markup.
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "./ui";
import {
  clipUrl, encodeWav, fetchAsk, fetchAsksStatus, startAsk, startAskUpload,
  type AskClip, type AskJob, type AskSample, type AsksStatus, type ClaimResult,
} from "@/lib/ask";
import { HOSTED } from "@/lib/config";
import { viewKey } from "@/lib/live";

const usd = (n: number | null | undefined) => (n === null || n === undefined ? "n/a" : `$${n.toFixed(n < 0.01 ? 5 : 4)}`);
const cap = (n: number) => `$${n.toFixed(2)}`;
const KEY = "diocle-ask-job";
const MAX_SECONDS = 10;
const TONE = { confirmed: "green", refuted: "red", unchecked: "amber" } as const;

function remember(id: string | null) {
  try { if (id) sessionStorage.setItem(KEY, id); else sessionStorage.removeItem(KEY); } catch { /* the page works without it */ }
}
function recall(): string | null {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}
const fields = (v: Record<string, string> | undefined) => Object.entries(v ?? {}).map(([k, x]) => `${k} = ${x}`).join(", ");

export default function AskPanel() {
  const [status, setStatus] = useState<AsksStatus | null | "unreachable">(null);
  const [clip, setClip] = useState<AskClip>("fee-overdrawn");
  const [job, setJob] = useState<AskJob | null>(null);
  const [watch, setWatch] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [recording, setRecording] = useState<number | null>(null);  // seconds so far, while the microphone is open
  const stopRec = useRef<(() => void) | null>(null);
  const cancelRec = useRef<(() => void) | null>(null);
  const opening = useRef(false);
  const mounted = useRef(true);

  const refresh = useCallback(() => {
    fetchAsksStatus().then((s) => setStatus(s ?? "unreachable")).catch(() => setStatus("unreachable"));
  }, []);
  const follow = useCallback((id: string) => { setWatch(id); remember(id); setError(null); }, []);

  useEffect(() => {
    refresh();
    const old = recall();
    if (old) follow(old);
  }, [refresh, follow]);

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
      let delay = 1000;
      try {
        const j = await fetchAsk(id);
        if (stop) return;
        failures = 0;
        setJob(j);
        if (j.status !== "running") { again = false; refresh(); }
      } catch {
        failures += 1;
        if (failures >= 8) { again = false; setError("The engine could not be reached; stopped checking. Reload the page to try again."); }
        else if (!stop) { setError("The engine could not be reached just now; trying again."); delay = Math.min(15000, 1000 * 2 ** failures); }
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

  const s = status && status !== "unreachable" ? status : null;
  const info = s?.clips.find((c) => c.clip === clip);
  const running = job?.status === "running";

  const begin = async (go: () => Promise<string>) => {
    setStarting(true); setError(null); setJob(null);
    try { follow(await go()); } catch (e) { setError(e instanceof Error ? e.message : "The request failed."); refresh(); } finally { setStarting(false); }
  };

  const reason: string | null =
    status === "unreachable" ? "The engine could not be reached, so there is nothing to run."
      : status === null ? "Checking what this engine allows…"
        : !s ? "This engine does not offer the ask button."
          : running ? "A question is running; the button comes back when it finishes."
            : starting ? "Starting…" : s.reason;

  // The microphone, when the engine says this caller may send a clip, under its own caps.
  const micAllowed = !!s?.uploadsAllowed && !!info;
  const micReason = running || starting ? reason : s?.uploadReason ?? null;
  const record = async () => {
    if (!info || opening.current || stopRec.current) return;  // one recording at a time, even on a double click
    opening.current = true;
    setError(null);
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1 } });
      const opened = stream;
      if (!mounted.current) {  // the visitor left while the permission prompt or device was opening: record nothing
        opened.getTracks().forEach((t) => t.stop());
        return;
      }
      ctx = new AudioContext();  // at the device's own rate (some browsers refuse any other); encodeWav averages it down to 16 kHz
      const audio = ctx;
      const rate = audio.sampleRate;
      const limit = Math.floor(rate * MAX_SECONDS);
      const src = audio.createMediaStreamSource(opened);
      const node = audio.createScriptProcessor(4096, 1, 1);
      const chunks: Float32Array[] = [];
      let total = 0;
      let done = false;
      const stop = () => {
        if (done) return;
        done = true;
        node.disconnect(); src.disconnect(); opened.getTracks().forEach((t) => t.stop());
        audio.close().catch(() => undefined);
        clearInterval(tick);
        stopRec.current = null;
        cancelRec.current = null;
        setRecording(null);
      };
      const finish = () => {
        if (done) return;
        stop();
        const all = new Float32Array(total);
        let o = 0;
        for (const c of chunks) { all.set(c, o); o += c.length; }
        if (total / rate < 0.4) { setError("That was too short; hold the button a little longer."); return; }
        void begin(() => startAskUpload(info.sample as AskSample, encodeWav(all.subarray(0, Math.min(total, limit)), rate)));
      };
      node.onaudioprocess = (e) => {
        if (done) return;
        const d = new Float32Array(e.inputBuffer.getChannelData(0));
        chunks.push(d); total += d.length;
        if (total >= limit) finish();
      };
      src.connect(node); node.connect(audio.destination);
      const t0 = Date.now();
      const tick = setInterval(() => setRecording(Math.min(MAX_SECONDS, (Date.now() - t0) / 1000)), 200);
      stopRec.current = finish;
      cancelRec.current = stop;
      setRecording(0);
    } catch {
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => undefined);
      setError("The microphone could not be opened (permission denied, no microphone, or this browser cannot record here).");
    } finally {
      opening.current = false;
    }
  };
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; cancelRec.current?.(); };  // leaving the page stops the microphone and sends nothing
  }, []);

  return (
    <section className="panel live ask" id="ask" aria-labelledby="ask-h">
      <div className="panel-heading">
        <div>
          <h2 id="ask-h">Ask the original program</h2>
          <p>Ask out loud: Muse Spark proposes claims about the program, and GnuCOBOL runs the original to check them.</p>
        </div>
      </div>
      <div className="live-cards">
        {(s?.clips ?? []).map((c) => (
          <div key={c.clip} className={`live-card ask-clip${c.clip === clip ? " on" : ""}`}>
            <h3>
              <label>
                <input type="radio" name="ask-clip" value={c.clip} checked={c.clip === clip} disabled={running || starting}
                  onChange={() => setClip(c.clip)} />{" "}
                Question about <span className="mono">{c.sample}</span>
              </label>
            </h3>
            <p className="ask-q">&ldquo;{c.question}&rdquo;</p>
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <audio controls preload="none" src={clipUrl(c.clip)} aria-label={`Spoken question: ${c.question}`} />
            <p className="live-caps">Recorded by the author ({c.seconds.toFixed(1)} s).</p>
          </div>
        ))}
        {status === null && <p className="live-caps">Checking what this engine allows…</p>}
      </div>
      <div className="ask-actions">
        <button type="button" className="button primary" disabled={reason !== null || !info}
          onClick={() => info && begin(() => startAsk(info.sample, info.clip))}>Ask the original program</button>
        {micAllowed && recording === null && (
          <button type="button" className="button secondary" disabled={micReason !== null}
            onClick={record}>Ask in my own voice (up to {MAX_SECONDS} s) about {info?.sample}</button>
        )}
        {recording !== null && (
          <button type="button" className="button secondary ask-rec" onClick={() => stopRec.current?.()}>
            <span className="ask-rec-dot" aria-hidden="true" /> Recording {recording.toFixed(1)} s of {MAX_SECONDS}. Press to stop and ask
          </button>
        )}
      </div>
      {reason && <p className="live-reason" role="status">{reason.startsWith("Checking") ? reason : `Disabled: ${reason}`}</p>}
      {micAllowed && micReason && <p className="live-reason" role="status">Your own voice is not available now: {micReason}</p>}
      {micAllowed && !micReason && <p className="live-caps">Your own voice goes to Meta&apos;s speech service: please leave out names and real account details.</p>}
      <details className="inline-more live-limits" id="ask-limits">
        <summary>Limits and privacy</summary>
        <p>
          Play a question, press Ask, and watch it travel: <strong>Muse Voice Transcribe</strong> writes down what was said,
          a <strong>Muse Spark</strong> model turns it into claims about the COBOL program with concrete examples, and then
          <strong> GnuCOBOL runs the original program</strong> on those examples. The answer below is put together only from
          claims GnuCOBOL confirmed; the models propose, they never decide. Use one of two bundled clips, or ask in your own voice
          about the same program. Your words are treated as data, never as instructions, and they cannot change what GnuCOBOL decides.
        </p>
        <p>
          At most {cap(s?.maxUsd ?? 0.01)} per question.{" "}
          {s ? `${s.visitorLeft} left for you now. Limits per 24 hours: ${s.perVisitorPerDay} per visitor and ${s.perDay} overall (${s.usedToday} used in the last 24 hours).` : "Loading limits."}
          {" "}One live job runs at a time.
        </p>
        {micAllowed && (
          <p>
            <strong>Your own voice:</strong> recording starts only when you press the button.{" "}
            {s?.uploadPerVisitorPerDay !== undefined && <>{s.uploadPerVisitorPerDay} recorded questions per visitor per day, {s.uploadPerDay} a day overall ({s.uploadVisitorLeft} left for you), at most {usd(s.maxUsd)} each. </>}
            {HOSTED
              ? <>The clip goes to Meta&apos;s speech service. Only you can read the answer here; the clip is deleted when the job ends, and the transcript an hour later. Please leave out names and real account details.</>
              : <>This is your local engine: the clip goes to Meta&apos;s speech service with your key and stays in this machine&apos;s runs folder.</>}
          </p>
        )}
      </details>
      {error && <p className="live-error" role="alert">{error}</p>}
      {job && (viewKey(job.id) && job.status !== "running" && !job.result && !job.error
        ? <p className="live-caps" role="status">The answer to this question has been removed: results are kept for an hour.</p>
        : <Stages job={job} />)}
    </section>
  );
}

function Step({ n, title, state, children }: { n: number; title: string; state: "wait" | "active" | "done" | "failed" | "not-run"; children?: React.ReactNode }) {
  return (
    <li className={`ask-step is-${state}`}>
      <h4>
        <span className="ask-n">{n}</span> {title}{" "}
        <Badge tone={state === "done" ? "green" : state === "active" ? "amber" : state === "failed" ? "red" : "neutral"}>
          {state === "done" ? "DONE" : state === "active" ? "RUNNING" : state === "failed" ? "STOPPED" : state === "not-run" ? "NOT RUN" : "WAITING"}
        </Badge>
      </h4>
      {children}
    </li>
  );
}

function Stages({ job }: { job: AskJob }) {
  const r = job.result;
  const t = r?.transcript ?? job.partial?.transcript ?? null;
  const proposed = r ? r.behavior.claims.map((c) => c.statement) : job.partial?.proposed ?? null;
  const failed = job.status === "failed";
  const order = ["starting", "transcribing", "claims", "checking", "answering", "done"];
  const at = order.indexOf(job.stage);
  const st = (i: number, done: boolean): "wait" | "active" | "done" | "failed" =>
    done ? "done" : failed && at <= i ? (at === i || at < 0 ? "failed" : "wait") : job.status === "running" && at === i ? "active" : "wait";
  const claimsDone = !!proposed;
  const checkDone = !!r;
  const nothingRan = !!r && r.behavior.claims.length === 0;
  return (
    <div className="live-run ask-run" aria-labelledby="ask-run-h">
      <h3 id="ask-run-h">
        <Badge tone={job.status === "running" ? "amber" : failed ? "red" : "green"}>
          {job.status === "running" ? "LIVE, running now" : failed ? "STOPPED" : "FINISHED"}
        </Badge>{" "}
        Question <span className="mono">{job.id}</span>
      </h3>
      <ol className="ask-steps">
        <Step n={1} title="Transcribe: Muse Voice Transcribe" state={st(1, !!t)}>
          {t ? (
            <p>
              Heard: <q className="ask-heard">{t.text}</q>{" "}
              <small className="mono">
                {t.model ?? "typed text, no transcription"}{t.model ? ` · ${t.audioSeconds.toFixed(1)} s of audio · ${usd(t.costUsd)}` : ""}
                {t.model && !t.priceConfirmed ? " (price is our estimate, not a published price)" : ""}
              </small>
            </p>
          ) : <p className="live-caps">Streaming the audio to the speech model…</p>}
        </Step>
        <Step n={2} title={`Claims: ${r?.behavior.model ?? "Muse Spark"} proposes`} state={st(2, claimsDone)}>
          {proposed ? (
            <>
              {proposed.length > 0 && <p className="live-caps">Proposed by a model. Not yet checked: these are guesses until GnuCOBOL has run them.</p>}
              <ul>{proposed.map((p, i) => <li key={i}>{p}</li>)}</ul>
              {proposed.length === 0 && <p className="live-caps">The model wrote no usable claim.</p>}
            </>
          ) : <p className="live-caps">The model is writing claims with examples…</p>}
        </Step>
        <Step n={3} title="GnuCOBOL runs the original program on the examples" state={nothingRan ? "not-run" : st(3, checkDone)}>
          {r ? <Verdicts claims={r.behavior.claims} /> : <p className="live-caps">{claimsDone ? "Compiling the original COBOL and running every example in the sandbox…" : "Waiting for the claims."}</p>}
        </Step>
        <Step n={4} title="Answer, assembled only from confirmed claims" state={st(4, checkDone)}>
          {r ? (
            <>
              <pre className="ask-answer" tabIndex={0} aria-label="The assembled answer">{r.answer.text}</pre>
              {r.answer.basis === "confirmed-claims" && (
                <p className="ask-decided">
                  <strong>GnuCOBOL decided, not the model; confirmed on the examples tried.</strong> That is not a proof for every input.
                </p>
              )}
            </>
          ) : <p className="live-caps">Nothing is shown here until GnuCOBOL has decided.</p>}
        </Step>
      </ol>
      {r && (
        <p className="live-caps">
          Cost: transcription {usd(r.costs.transcribeUsd)} + claims {usd(r.costs.claimsUsd)} = {usd(r.costs.totalUsd)} of a {usd(r.caps.maxUsd)} cap.
          Verdicts: {r.verdict.confirmed} confirmed, {r.verdict.refuted} refuted, {r.verdict.unchecked} unchecked.
          {r.stopped ? ` Stopped early: ${r.stopped}.` : ""}
        </p>
      )}
      {failed && <p className="live-error" role="alert">The question stopped: {job.error}. Nothing is claimed about this program.</p>}
      <details className="ask-events">
        <summary>What the engine reported, in order</summary>
        <ol className="live-events">{job.events.map((e, i) => <li key={i}>{e.message}</li>)}</ol>
      </details>
    </div>
  );
}

function Verdicts({ claims }: { claims: ClaimResult[] }) {
  if (claims.length === 0) return <p className="live-caps">No claim to run.</p>;
  return (
    <ul className="ask-claims">
      {claims.map((c) => (
        <li key={c.id}>
          <Badge tone={TONE[c.status]}>{c.status.toUpperCase()}</Badge> {c.statement}
          {c.reason && <small className="live-caps"> ({c.reason})</small>}
          <ul>
            {c.examples.map((e) => (
              <li key={e.id} className="mono">
                {e.id} {e.status}: input ({fields(e.inputs[0])})
                {e.actual?.records?.[0] ? <> → GnuCOBOL produced ({fields(e.actual.records[0])})</> : null}
                {(e.mismatches ?? []).map((m, i) => (
                  <div key={i} className="ask-refuted">refuted at {m.what}: the claim expected {m.expected}, GnuCOBOL produced {m.actual}</div>
                ))}
                {e.reason && <div className="live-caps">{e.reason}</div>}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}
