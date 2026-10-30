"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { CANONICAL, CANONICAL_FRESH_INPUTS, GLOSSARY, LINKS, SAMPLE_RUN } from "@/lib/config";
import { fetchRun, fetchRunSchema, fetchRunSource, fetchRuns, reverifyRun, schemaFile, type Reverify, type Run, type RunListItem, type SourceFile } from "@/lib/runs";
import { SAMPLE_COBOL, SAMPLE_RECORDED } from "@/lib/sample";
import { SourcePane } from "./runs-view";
import { Term } from "./ui";

type Go = (view: "Delivery" | "Live runs" | "Evidence") => void;

const usd = (n: number) => `$${n.toFixed(2)}`;

// Turns a verifier diff string ("FIELD: original X converted Y") into a sentence a stranger can read. CL-FEE is the fee
// CHQCLR charges when a cheque is returned for insufficient funds (NSF); the COBOL doubles the base fee. The sample has no
// currency code, so none is shown.
function explainDiff(diff: string | undefined): string {
  const m = diff?.match(/^([\w-]+): original (.+?) converted (.+)$/);
  if (!m) return diff ?? "";
  const [, field, was, now] = m;
  if (field === "CL-FEE") {
    return `The return fee (doubled for NSF returns, i.e. cheques returned for insufficient funds): the COBOL charged ${was}; the AI-written Java charged ${now}. The unit is not stated in the COBOL.`;
  }
  return `Field ${field}: the COBOL wrote ${was}; the AI-written Java wrote ${now}.`;
}

// The verdict strip tells the sample's real story: certified, broken by the breaker agent, repaired, re-certified.
function VerdictStrip({ run, offline, check }: { run: Run | null; offline: boolean; check: Reverify | null }) {
  const broke = run?.breaker?.counterexamples.map((c) => c.diff) ?? SAMPLE_RECORDED.broke;
  const tried = run?.breaker?.tried ?? SAMPLE_RECORDED.tried;
  const final = run?.after ? `${run.after.passed.toLocaleString()}/${run.after.total.toLocaleString()}` : `${SAMPLE_RECORDED.finalHeldOut.toLocaleString()}/${SAMPLE_RECORDED.finalHeldOut.toLocaleString()}`;
  const frames = [
    { tone: "bad", head: "BREAKER AGENT", text: explainDiff(broke[0]) },
    { tone: "busy", head: "REPAIR AGENT", text: `${broke.length} of ${tried} designed inputs broke it · patched, compiled, re-tested` },
    { tone: "ok", head: "CERTIFIED", text: `${final} held-out inputs matched` },
  ];
  const [at, setAt] = useState(0);
  useEffect(() => {
    if (check || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setAt((i) => (i + 1) % frames.length), 2600);
    return () => clearInterval(t);
  }, [check, frames.length]);
  if (check) {
    return (
      <div className={`verdict-strip verdict-${check.allMatch ? "ok" : "bad"}`} role="status">
        <strong>{check.allMatch ? "RE-VERIFIED NOW" : "DIFFERENCE FOUND"}</strong>
        <span>
          seed {check.seed} · {check.passed.toLocaleString()}/{check.total.toLocaleString()} inputs match ·
          stdout {check.stdoutMatch ? "matches" : "differs"} · byte for byte · {check.seconds}s · no model involved
          {check.firstMismatch ? ` · first difference: ${check.firstMismatch}` : ""}
        </span>
      </div>
    );
  }
  const f = frames[at];
  return (
    <div className={`verdict-strip verdict-${f.tone}`} role="status" aria-live="off">
      <strong>{f.head}</strong>
      <span>{f.text}</span>
      <span className="verdict-steps" aria-hidden="true">
        {frames.map((x, i) => <i key={x.head} className={i === at ? "on" : ""} />)}
      </span>
      {offline && <small className="verdict-offline">engine unreachable: recorded result of run {SAMPLE_RUN.id}</small>}
    </div>
  );
}

function SampleHero({ go }: { go: Go }) {
  const [run, setRun] = useState<Run | null>(null);
  const [offline, setOffline] = useState(false);
  const [cobol, setCobol] = useState<SourceFile[]>(SAMPLE_COBOL);
  const [java, setJava] = useState<SourceFile[] | null>(null);
  const [sql, setSql] = useState<SourceFile | null>(null);
  const [cobolAt, setCobolAt] = useState(0);
  const [javaAt, setJavaAt] = useState(0);
  const [check, setCheck] = useState<Reverify | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    fetchRun(SAMPLE_RUN.id).then(setRun).catch(() => setOffline(true));
    fetchRunSource(SAMPLE_RUN.id)
      .then((s) => {
        if (s.cobol.length) setCobol(s.cobol);
        setJava(s.java);
      })
      .catch(() => setJava([]));
    fetchRunSchema(SAMPLE_RUN.id).then((s) => setSql(schemaFile(s))).catch(() => setSql(null));  // older engines: Java only
  }, []);
  async function tryIt() {
    setBusy(true);
    setError("");
    try {
      setCheck(await reverifyRun(SAMPLE_RUN.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel sample-hero">
      <div className="panel-heading">
        <div>
          <h2>{SAMPLE_RUN.program}: cheque clearing, COBOL → Java</h2>
          <p>A synthetic program Muse Spark had never seen. Left: the original. Right: the Java Diocle certified{sql ? ", and its copybooks as SQL tables (schema.sql)" : ""}.</p>
        </div>
      </div>
      <div className="source-split">
        <SourcePane label="COBOL" files={cobol} at={cobolAt} pick={setCobolAt} />
        <SourcePane label={java?.length && sql ? "JAVA · SQL" : "JAVA"} files={java?.length && sql ? [...java, sql] : java ?? []}
          at={javaAt} pick={setJavaAt}
          placeholder={java === null ? "Loading the certified Java…" : "The certified Java could not be loaded from the engine.\nOpen the full run for its trace, checks and\nthe re-verify button."} />
      </div>
      <VerdictStrip run={run} offline={offline} check={check} />
      <div className="home-actions sample-actions">
        <button className="button primary sample-try" disabled={busy} onClick={tryIt}>
          {busy ? "Running COBOL and Java on fresh inputs…" : `▶ Try the sample (${SAMPLE_RUN.program})`}
        </button>
        <button className="button secondary" onClick={() => {
          window.history.pushState(null, "", `/runs#run=${encodeURIComponent(SAMPLE_RUN.id)}`);
          go("Live runs");
        }}>Open the full run</button>
        <a className="button secondary" href="/mission#live">Try it live: convert a sample now</a>
        <a className="button secondary" href="/mission">Watch the agents work (replay)</a>
        <a className="button secondary" href="/bugs">Bug of the day</a>
        <a className="button secondary" href="/evidence">Cost and speed scoreboard</a>
        <span className="sample-note">
          Re-runs the original under <Term tip={GLOSSARY.GnuCOBOL}>GnuCOBOL</Term> and the certified Java on about
          1,000 inputs from a seed chosen now, and compares every byte. Takes a few seconds.
        </span>
      </div>
      {error && <p className="dlv-error sample-error">{error}</p>}
    </section>
  );
}

function Evidence({ go }: { go: Go }) {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  useEffect(() => {
    fetchRuns().then(setRuns).catch(() => setRuns([]));
  }, []);
  const certified = runs?.filter((r) => r.certified && !r.sampleRun).length ?? 0;  // live sample runs are real but not counted here
  const repaired = runs?.filter((r) => r.assurance === "certified-against-repaired-cobol").length ?? 0;  // never inside "certified"
  const unverified = runs?.filter((r) => r.assurance === "compiled-unverified").length ?? 0;
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Evidence</h2>
          <p>One delivery to check end to end, and every attempt this engine has kept.</p>
        </div>
      </div>
      <dl className="eff-grid home-evidence">
        <div><dt>Programs in {CANONICAL.pr}</dt><dd className="mono">{CANONICAL.programs.length}/{CANONICAL.programs.length}</dd></div>
        <div><dt>Fresh inputs in its CI</dt><dd className="mono">{CANONICAL_FRESH_INPUTS.toLocaleString()}</dd></div>
        <div><dt>Differences</dt><dd className="mono">{CANONICAL.differences}</dd></div>
        <div><dt>All runs on this engine</dt><dd className="mono">{runs ? `${certified}/${runs.length}` : "…"}</dd></div>
        {repaired > 0 && <div><dt>Verified against repaired COBOL (not certified)</dt><dd className="mono">{repaired}</dd></div>}
        {unverified > 0 && <div><dt>Compiled, not verified</dt><dd className="mono">{unverified}</dd></div>}
      </dl>
      <p className="home-pr">
        <strong>{CANONICAL.programs.length}/{CANONICAL.programs.length}</strong> is the canonical delivery,
        {" "}<a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a>, re-verified by that
        repository&apos;s own <a href={LINKS.evidenceCi} target="_blank" rel="noreferrer">CI run</a>; about
        {" "}{usd(CANONICAL.modelSpendUsd)} of model spend for the six conversions (estimated from list prices).
        {" "}<strong>{runs ? `${certified}/${runs.length}` : "…"}</strong> counts every run this engine has kept,
        including failed and interrupted attempts. <button type="button" className="link-button" onClick={() => go("Evidence")}>All evidence</button>
      </p>
    </section>
  );
}

const COBOL_KEY = "diocle.whatIsCobol.open";

// A 20-second primer for visitors who do not know COBOL. Open on a first visit; the choice is remembered (localStorage may
// be unavailable, so every access is guarded and the box simply stays open).
function WhatIsCobol() {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    try {
      if (window.localStorage.getItem(COBOL_KEY) === "closed") setOpen(false);
    } catch { /* storage blocked: keep the default */ }
  }, []);
  function toggle() {
    const next = !open;
    setOpen(next);
    try { window.localStorage.setItem(COBOL_KEY, next ? "open" : "closed"); } catch { /* ignore */ }
  }
  return (
    <section className="panel cobol-primer" aria-label="What is COBOL">
      <button type="button" className="cobol-primer-toggle" aria-expanded={open} aria-controls="cobol-primer-body" onClick={toggle}>
        <strong>What is COBOL? (20 seconds)</strong>
        <span aria-hidden="true">{open ? "hide" : "show"}</span>
      </button>
      {open && (
        <p id="cobol-primer-body" className="cobol-primer-body">
          COBOL is a programming language from 1959 that still runs the nightly <em>batch jobs</em> (programs that
          process a whole day of records at once) at banks: adding interest, charging fees, posting transactions.
          These programs are decades old and hold rules nobody fully remembers, so nobody wants to touch them. AI can
          now rewrite one in Java in minutes; the risk is a silent wrong cent on some input. Diocle runs the old
          program and the new Java on the same inputs and compares every byte.
        </p>
      )}
    </section>
  );
}

const STEPS: [string, React.ReactNode][] = [
  ["ANALYZE", <>Reads a mainframe library export: programs, <Term tip={GLOSSARY.copybook}>copybooks</Term>, <Term tip={GLOSSARY.JCL}>JCL</Term> and procedures. Derives every record layout byte by byte and flags behaviour a rewrite must keep.</>],
  ["CONVERT", <>Meta Muse Spark translates each program to Java. A repair agent, also Muse Spark, reads failures, patches, compiles and re-tests until it matches.</>],
  ["CHECK", <>The original COBOL and the Java run on the same inputs. Every field, byte, display line and return code must agree, including on 1,000 <Term tip={GLOSSARY["held-out"]}>held-out</Term> inputs. Then a breaker agent tries to break it.</>],
  ["DELIVER", <>Each program that passes goes to the target repository as a pull request with an equivalence report. That repository&apos;s CI repeats the check on fresh inputs.</>],
];

export default function HomeView({ go }: { go: Go }) {
  return (
    <div className="view-content home">
      <section className="panel home-hero">
        <div className="panel-heading">
          <div>
            <h2>DIOCLE.EXE</h2>
            <p>COBOL to Java, checked against the original</p>
          </div>
        </div>
        <div className="home-hero-body">
          <h1>AI writes the code.<br />Diocle checks it against the original before anyone has to trust it.</h1>
          <p>
            Banks still move money through COBOL written decades ago, and the people who wrote it are retiring.
            Converting it is the easy part; knowing the new code rounds, truncates and overflows exactly like the old
            code is the hard part, and today it is checked by hand. Diocle makes that check automatic, repeatable and
            inspectable.
          </p>
          <p className="home-meta">
            Built with <strong>Meta Muse Spark</strong> as translator, repair agent and breaker agent, and
            {" "}<strong>Muse Spark Open</strong> (open weights) for private mode. No other model is used.
          </p>
          <p className="home-meta">
            &ldquo;Certified&rdquo; here means <strong>matched on the tested inputs, not proven equivalent</strong>
            {" "}(<a href={LINKS.certified} target="_blank" rel="noreferrer">definition and limits</a>). Synthetic programs only; GnuCOBOL, SQLite and Berkeley DB stand in for z/OS COBOL, DB2 and VSAM.
          </p>
        </div>
      </section>

      <section className="panel home-headline" aria-label="Measured result">
        <div className="panel-heading">
          <div>
            <h2>Measured: passing the test is not the same as being right</h2>
            <p>15 synthetic COBOL programs, Muse Spark, GnuCOBOL as the judge</p>
          </div>
        </div>
        <dl className="eff-grid home-evidence">
          <div><dt>First translations passing 1,000 held-out inputs (3 tries x 15 programs)</dt><dd className="mono">37/45</dd></div>
          <div><dt>Test-passing translations still wrong when attacked</dt><dd className="mono">4/10</dd></div>
          <div><dt>Programs certified by a full Diocle run</dt><dd className="mono">14/15</dd></div>
        </dl>
        <p className="home-pr">
          In a separate attack run (one fresh translation per program), four of the ten translations that passed the
          1,000-input test and could be attacked were broken by the breaker agent&apos;s designed inputs; three of those four had
          passed all three first-try trials. One program, CHQCLR, was not certified. Small sample, one model, synthetic
          programs, about $0.69 of model spend: <a href={LINKS.measurement} target="_blank" rel="noreferrer">method, per-program table and caveats <ExternalLink size={11} /></a>.
        </p>
      </section>

      <WhatIsCobol />

      <SampleHero go={go} />

      <div className="home-steps">
        {STEPS.map(([title, text], i) => (
          <section key={title} className="panel home-step">
            <div className="panel-heading"><div><h2>{i + 1}. {title}</h2></div></div>
            <p>{text}</p>
          </section>
        ))}
      </div>

      <Evidence go={go} />

      <div className="home-columns">
        <section className="panel">
          <div className="panel-heading"><div><h2>What “certified” means</h2></div></div>
          <ul className="home-list">
            <li>On every input tried, the Java’s records, display output and exit code equal the original’s.</li>
            <li>The original is compiled with <Term tip={GLOSSARY.GnuCOBOL}>GnuCOBOL</Term> 3.2 under IBM’s <Term tip={GLOSSARY["TRUNC(STD)"]}>TRUNC(STD)</Term> and DISPLAY defaults, in <Term tip={GLOSSARY.EBCDIC}>EBCDIC</Term> collating order.</li>
            <li>Where captured mainframe output exists, the mainframe is the judge instead.</li>
          </ul>
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h2>What it does not mean</h2></div></div>
          <ul className="home-list">
            <li>Equivalence for every possible input: testing cannot show that.</li>
            <li>Equivalence to IBM COBOL where GnuCOBOL differs and no mainframe output was captured.</li>
            <li>Support for <Term tip={GLOSSARY.CICS}>CICS</Term>, <Term tip={GLOSSARY.DB2}>DB2</Term> or <Term tip={GLOSSARY.VSAM}>VSAM</Term> updates: those programs are reported, not converted.</li>
          </ul>
          <p className="home-more"><a href={LINKS.certified} target="_blank" rel="noreferrer">Full definition and limits</a></p>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><h2>Sample estate</h2><p>Quillmark Trust &amp; Savings is a fictional bank shipped with Diocle so you can see it work end to end. Its programs and data are synthetic.</p></div></div>
        <ul className="home-list home-links">
          <li><a href={LINKS.legacy} target="_blank" rel="noreferrer">quillmark-mainframe</a>: an export of z/OS libraries (COBOL, copybooks, JCL, procedures, DB2, CICS, IMS, EBCDIC extracts).</li>
          <li><a href={LINKS.target} target="_blank" rel="noreferrer">quillmark-java</a>: starts empty; Diocle delivers certified programs as pull requests and its CI re-checks them.</li>
          <li><a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a>: re-delivers INTACCR, and the repository&apos;s CI re-verifies all six programs under one pinned verifier on {CANONICAL_FRESH_INPUTS.toLocaleString()} fresh inputs.</li>
          <li><a href={LINKS.buildLog} target="_blank" rel="noreferrer">Build log</a>: what was built during the hackathon, including the mistakes we found.</li>
        </ul>
        <p className="home-more"><a href={LINKS.diocle} target="_blank" rel="noreferrer">Source on GitHub <ExternalLink size={11} /></a></p>
      </section>
    </div>
  );
}
