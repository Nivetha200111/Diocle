"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { CANONICAL, CANONICAL_FRESH_INPUTS, GLOSSARY, LINKS, SAMPLE_RUN } from "@/lib/config";
import { fetchRun, fetchRunSource, fetchRuns, reverifyRun, type Reverify, type Run, type RunListItem, type SourceFile } from "@/lib/runs";
import { SAMPLE_COBOL, SAMPLE_RECORDED } from "@/lib/sample";
import { SourcePane } from "./runs-view";
import { Term } from "./ui";

type Go = (view: "Delivery" | "Live runs" | "Evidence") => void;

const usd = (n: number) => `$${n.toFixed(2)}`;

// The verdict strip tells the sample's real story: certified, broken by the breaker agent, repaired, re-certified.
function VerdictStrip({ run, offline, check }: { run: Run | null; offline: boolean; check: Reverify | null }) {
  const broke = run?.breaker?.counterexamples.map((c) => c.diff) ?? SAMPLE_RECORDED.broke;
  const tried = run?.breaker?.tried ?? SAMPLE_RECORDED.tried;
  const final = run?.after ? `${run.after.passed.toLocaleString()}/${run.after.total.toLocaleString()}` : `${SAMPLE_RECORDED.finalHeldOut.toLocaleString()}/${SAMPLE_RECORDED.finalHeldOut.toLocaleString()}`;
  const frames = [
    { tone: "bad", head: "BREAKER AGENT", text: `${broke[0]?.replace(": original ", "  original ").replace(" converted ", "  ≠  Java ")}` },
    { tone: "busy", head: "REPAIR AGENT", text: `${broke.length} of ${tried} designed inputs broke it · patched, compiled, re-tested` },
    { tone: "ok", head: "CERTIFIED", text: `${final} held-out inputs match, byte for byte` },
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
          stdout {check.stdoutMatch ? "matches" : "differs"} · {check.seconds}s · no model involved
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
          <p>A synthetic program Muse Spark had never seen. Left: the original. Right: the Java Diocle certified.</p>
        </div>
      </div>
      <div className="source-split">
        <SourcePane label="COBOL" files={cobol} at={cobolAt} pick={setCobolAt} />
        <SourcePane label="JAVA" files={java ?? []} at={javaAt} pick={setJavaAt}
          placeholder={java === null ? "Loading the certified Java…" : "The certified Java could not be loaded from the engine.\nOpen the full run for its trace, checks and\nthe re-verify button."} />
      </div>
      <VerdictStrip run={run} offline={offline} check={check} />
      <div className="home-actions sample-actions">
        <button className="button primary sample-try" disabled={busy} onClick={tryIt}>
          {busy ? "Running COBOL and Java on fresh inputs…" : `▶ Try the sample (${SAMPLE_RUN.program})`}
        </button>
        <button className="button secondary" onClick={() => {
          window.location.hash = `run=${SAMPLE_RUN.id}`;
          go("Live runs");
        }}>Open the full run</button>
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
  const certified = runs?.filter((r) => r.certified).length ?? 0;
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
      </dl>
      <p className="home-pr">
        <strong>{CANONICAL.programs.length}/{CANONICAL.programs.length}</strong> is the latest delivery,
        {" "}<a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a>, re-verified by that
        repository&apos;s own <a href={LINKS.evidenceCi} target="_blank" rel="noreferrer">CI run</a>; about
        {" "}{usd(CANONICAL.modelSpendUsd)} of model spend for the six conversions (estimated from list prices).
        {" "}<strong>{runs ? `${certified}/${runs.length}` : "…"}</strong> counts every run this engine has kept,
        including failed and interrupted attempts. <button type="button" className="link-button" onClick={() => go("Evidence")}>All evidence</button>
      </p>
    </section>
  );
}

const STEPS: [string, React.ReactNode][] = [
  ["ANALYZE", <>Reads a mainframe library export: programs, <Term tip={GLOSSARY.copybook}>copybooks</Term>, <Term tip={GLOSSARY.JCL}>JCL</Term> and procedures. Derives every record layout byte by byte and flags behaviour a rewrite must keep.</>],
  ["CONVERT", <>Meta Muse Spark translates each program to Java. A repair agent, also Muse Spark, reads failures, patches, compiles and re-tests until it matches.</>],
  ["CHECK", <>The original COBOL and the Java run on the same inputs. Every field, byte, display line and return code must agree, including on 1,000 <Term tip={GLOSSARY["held-out"]}>held-out</Term> inputs. Then a breaker agent tries to break it.</>],
  ["DELIVER", <>Each program that passes goes to the target repository as a pull request with a certificate. That repository&apos;s CI repeats the check on fresh inputs.</>],
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
        </div>
      </section>

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
          <li><a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a>: six programs under one pinned verifier, re-verified by GitHub CI on {CANONICAL_FRESH_INPUTS.toLocaleString()} fresh inputs.</li>
          <li><a href={LINKS.buildLog} target="_blank" rel="noreferrer">Build log</a>: what was built during the hackathon, including the mistakes we found.</li>
        </ul>
        <p className="home-more"><a href={LINKS.diocle} target="_blank" rel="noreferrer">Source on GitHub <ExternalLink size={11} /></a></p>
      </section>
    </div>
  );
}
