"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Mic } from "lucide-react";
import { CANONICAL, CANONICAL_FRESH_INPUTS, GLOSSARY, LINKS, SAMPLE_RUN } from "@/lib/config";
import { fetchRun, fetchRunSchema, fetchRunSource, fetchRuns, reverifyRun, schemaFile, type Reverify, type Run, type RunListItem, type SourceFile } from "@/lib/runs";
import { SAMPLE_COBOL, SAMPLE_RECORDED } from "@/lib/sample";
import { printoutImageUrl } from "@/lib/live";
import { SourcePane } from "./runs-view";
import { MEASURED_HINT, MEASURED_TITLE, MeasuredBody } from "./measured";
import { Fold, FoldLink, Term, useOpenOnHash } from "./ui";

type Go = (view: "Delivery" | "Live runs" | "Evidence" | "Try it live" | "Current run") => void;

const usd = (n: number) => `$${n.toFixed(2)}`;

// Turns a verifier diff string ("FIELD: original X converted Y") into a sentence a stranger can read. CL-FEE is the fee
// CHQCLR charges when a cheque is returned for insufficient funds (NSF); the COBOL doubles the base fee. The sample has no
// currency code, so none is shown.
function explainDiff(diff: string | undefined): string {
  const m = diff?.match(/^([\w-]+): original (.+?) converted (.+)$/);
  if (!m) return diff ?? "";
  const [, field, was, now] = m;
  if (field === "CL-FEE") {
    return `The return fee (doubled for NSF returns, i.e. cheques returned for insufficient funds), on a record whose fee field is malformed: the COBOL on GnuCOBOL charged ${was}; the AI-written Java charged ${now}. The unit is not stated in the COBOL.`;
  }
  return `Field ${field}: the COBOL wrote ${was}; the AI-written Java wrote ${now}.`;
}

// "Try the sample": a free re-check of the stored Java, no model. One state, so the button on the first screen and the one
// beside the source show the same result.
type SampleCheck = { check: Reverify | null; busy: boolean; error: string; tryIt: () => void };
function useSampleCheck(): SampleCheck {
  const [check, setCheck] = useState<Reverify | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
  return { check, busy, error, tryIt };
}

function CheckResult({ check }: { check: Reverify }) {
  return (
    <div className={`verdict-strip verdict-${check.allMatch ? "ok" : "bad"}`} role="status">
      <strong>{check.allMatch ? "RE-VERIFIED NOW" : "DIFFERENCE FOUND"}</strong>
      <span>
        seed {check.seed} · {check.passed.toLocaleString()}/{check.total.toLocaleString()} output records match ·
        stdout {check.stdoutMatch ? "matches" : "differs"} · byte for byte · {check.seconds}s · no model involved · on these records; a malformed blank return is known to differ
        {check.firstMismatch ? ` · first difference: ${check.firstMismatch}` : ""}
      </span>
    </div>
  );
}

// The catch's two amounts: from the stored run, or the recorded result if the engine cannot be reached.
function catchAmounts(run: Run | null): [string, string] {
  const diff = run?.breaker?.counterexamples[0]?.diff ?? SAMPLE_RECORDED.broke[0];
  const m = diff.match(/^([\w-]+): original (.+?) converted (.+)$/);
  return m ? [m[2], m[3]] : ["20.00", "0.00"];
}

const tryLabel = (busy: boolean) => (busy ? "Running COBOL and Java on fresh records…" : `Try the sample (${SAMPLE_RUN.program})`);

// The verdict strip tells the sample's real story: certified, broken by the breaker agent, repaired, re-certified.
function VerdictStrip({ run, offline, check }: { run: Run | null; offline: boolean; check: Reverify | null }) {
  const broke = run?.breaker?.counterexamples.map((c) => c.diff) ?? SAMPLE_RECORDED.broke;
  const tried = run?.breaker?.tried ?? SAMPLE_RECORDED.tried;
  const final = run?.after ? `${run.after.passed.toLocaleString()}/${run.after.total.toLocaleString()}` : `${SAMPLE_RECORDED.finalHeldOut.toLocaleString()}/${SAMPLE_RECORDED.finalHeldOut.toLocaleString()}`;
  const frames = [
    { tone: "bad", head: "BREAKER AGENT", text: explainDiff(broke[0]) },
    { tone: "busy", head: "REPAIR AGENT", text: `${broke.length} of ${tried} attack inputs (replays included) made it differ · patched, compiled, re-tested` },
    { tone: "ok", head: "CERTIFIED", text: `${final} output records matched on held-out generated inputs. Matched on the inputs tried, not proven equivalent: an audit later found a malformed record where this Java still differs` },
  ];
  const [at, setAt] = useState(0);
  useEffect(() => {
    if (check || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t = setInterval(() => setAt((i) => (i + 1) % frames.length), 2600);
    return () => clearInterval(t);
  }, [check, frames.length]);
  if (check) return <CheckResult check={check} />;
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

function SampleHero({ go, sample }: { go: Go; sample: SampleCheck }) {
  const [run, setRun] = useState<Run | null>(null);
  const [offline, setOffline] = useState(false);
  const [cobol, setCobol] = useState<SourceFile[]>(SAMPLE_COBOL);
  const [java, setJava] = useState<SourceFile[] | null>(null);
  const [sql, setSql] = useState<SourceFile | null>(null);
  const [cobolAt, setCobolAt] = useState(0);
  const [javaAt, setJavaAt] = useState(0);
  const { check, busy, error, tryIt } = sample;
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
  return (
    <section className="panel sample-hero" id="sample">
      <div className="panel-heading">
        <div>
          <h2>{SAMPLE_RUN.program}: cheque clearing, COBOL → Java</h2>
          <p>A synthetic program Muse Spark had never seen. Left: the original. Right: the Java Diocle certified{sql ? ", and its copybooks as SQL tables" : ""}.</p>
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
          {tryLabel(busy)}
        </button>
        <button className="button secondary" onClick={() => {
          window.history.pushState(null, "", `/runs#run=${encodeURIComponent(SAMPLE_RUN.id)}`);
          go("Live runs");
        }}>Open the full run</button>
        <a className="button secondary" href="/bugs">Bug of the day</a>
      </div>
      <details className="inline-more sample-more">
        <summary>What Try the sample does</summary>
        <p>
          Runs the original under <Term tip={GLOSSARY.GnuCOBOL}>GnuCOBOL</Term> and the certified Java once each on a file of about
          1,000 valid records from a seed chosen now, and compares every output byte. A re-check of stored Java: no model runs. Takes a few seconds.
        </p>
      </details>
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
    <Fold title="Evidence" hint="One delivery to check end to end, and every attempt this engine has kept.">
      <dl className="eff-grid home-evidence">
        <div><dt>Programs in {CANONICAL.pr}</dt><dd className="mono">{CANONICAL.programs.length}/{CANONICAL.programs.length}</dd></div>
        <div><dt>Fresh output records in its CI</dt><dd className="mono">{CANONICAL_FRESH_INPUTS.toLocaleString()}</dd></div>
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
        {" "}A larger one, from a second synthetic estate:{" "}
        <a href="https://github.com/Nivetha200111/harbor-trust-mainframe-java/pull/2" target="_blank" rel="noreferrer">harbor-trust-mainframe-java#2</a>,
        {" "}19 programs. Read its{" "}
        <a href="https://github.com/Nivetha200111/harbor-trust-mainframe-java/actions/runs/41301995356" target="_blank" rel="noreferrer">CI run</a>
        {" "}with care: for 18 of those programs the generated records give one identical placeholder line, so they were really exercised during conversion by records taken from the repository&apos;s data files, which CI does not have; the 19th only prints a line.
        {" "}<strong>{runs ? `${certified}/${runs.length}` : "…"}</strong> counts every run this engine has kept,
        including failed and interrupted attempts. <button type="button" className="link-button" onClick={() => go("Evidence")}>All evidence</button>
      </p>
    </Fold>
  );
}

// A 20-second primer for visitors who do not know COBOL.
function WhatIsCobol() {
  return (
    <Fold title="What is COBOL? (20 seconds)" className="cobol-primer">
      <p className="home-pr">
        COBOL is a programming language from 1959 that still runs the nightly <em>batch jobs</em> (programs that
        process a whole day of records at once) at banks: adding interest, charging fees, posting transactions.
        These programs are decades old and hold rules nobody fully remembers, so nobody wants to touch them. AI can
        now rewrite one in Java in minutes; the risk is a silent difference on some input. Diocle runs the old
        program (on GnuCOBOL) and the new Java on the same inputs and compares every output byte.
      </p>
    </Fold>
  );
}

// One glance on the first screen; the same steps in full sit in the "How it works" fold.
const STEPS: [string, string][] = [
  ["Translate", "Muse Spark writes the Java"],
  ["Compare", "Same inputs. No model decides"],
  ["Attack", "Muse Spark hunts differences, then repairs"],
  ["Deliver", "Pull request; its CI re-checks"],
];

const PIPELINE: [string, string, string][] = [
  ["Translate", "Muse Spark, as translator", "writes the Java from the COBOL; it never certifies"],
  ["Compare", "GnuCOBOL, no model", "runs the original and the Java on 1,000+ generated records; every output byte must match"],
  ["Attack", "Muse Spark, as breaker", "designs inputs aimed at Java that passed; Muse Spark, as repair agent with tools, fixes what differs"],
  ["Deliver", "Pull request", "the target repository's own CI re-runs the comparison on generated inputs"],
];

// The first screen: the question, one sentence, the actions, one real catch. Everything longer is one click away, below.
function Pitch({ go, sample, run }: { go: Go; sample: SampleCheck; run: Run | null }) {
  const [was, now] = catchAmounts(run);
  function openRun() {
    window.history.pushState(null, "", `/runs#run=${encodeURIComponent(SAMPLE_RUN.id)}`);
    go("Live runs");
  }
  return (
    <section className="panel pitch" aria-label="What Diocle does">
      <div className="pitch-top">
        <div className="pitch-claim">
          <h1>AI can rewrite COBOL in minutes. How do you know the Java still gives the same answer?</h1>
          <p className="pitch-sub">Diocle runs both on the same inputs and compares the output.</p>
          <div className="pitch-actions">
            <button type="button" className="button primary pitch-try" disabled={sample.busy} onClick={sample.tryIt}>{tryLabel(sample.busy)}</button>
            <button type="button" className="button secondary" onClick={() => go("Delivery")}>Import a COBOL repository</button>
            <a className="button secondary" href="/mission">Watch the agents work</a>
          </div>
          {sample.check && <div className="pitch-result"><CheckResult check={sample.check} /></div>}
          {sample.error && <p className="dlv-error pitch-result" role="alert">{sample.error}</p>}
          <p className="pitch-line">Testing on stated inputs under GnuCOBOL, not a formal proof. <FoldLink to="certified" also="not-certified">What certified means</FoldLink></p>
          <p className="pitch-line">Built Oct 27 to Nov 4, 2026, for the Meta Global AI Developer Hackathon. <a href={LINKS.buildLog} target="_blank" rel="noreferrer">Build log</a></p>
        </div>
        <figure className="pitch-catch">
          <figcaption>The catch · {SAMPLE_RUN.program}, cheque clearing</figcaption>
          <div className="pitch-row"><span>Original COBOL, on GnuCOBOL</span><strong className="pitch-ok mono">{was}</strong></div>
          <div className="pitch-row"><span>AI-written Java</span><strong className="pitch-bad mono">{now}</strong></div>
          <p className="pitch-fixed">Return fee on a malformed record, under GnuCOBOL. IBM&apos;s compiler not tested.</p>
          <button type="button" className="link-button" onClick={openRun}>Open this run and check it yourself</button>
        </figure>
      </div>
      <ol className="pitch-pipeline">
        {STEPS.map(([step, what], i) => [
          i > 0 && <li key={`${step}-arrow`} className="pitch-arrow" aria-hidden="true" />,
          <li key={step} className="pitch-step"><b>{i + 1}. {step}</b><span>{what}</span></li>,
        ])}
      </ol>
    </section>
  );
}

// What backs the catch: a number and a line each, the method one click away. Below the source, not on the first screen.
function Numbers({ go }: { go: Go }) {
  return (
    <section className="panel pitch" aria-label="The numbers">
      <dl className="pitch-numbers">
        <div><dt>translations that passed 1,000 generated records and could be attacked went on to differ, on malformed numbers or the sign of a zero. Synthetic programs. <FoldLink to="measured">How it was measured</FoldLink></dt><dd className="mono">4 of 10</dd></div>
        <div><dt>synthetic programs certified and delivered in one pull request, <a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a></dt><dd className="mono">{CANONICAL.programs.length}</dd></div>
        <div><dt>differences on {CANONICAL_FRESH_INPUTS.toLocaleString()} fresh output records in <a href={LINKS.evidenceCi} target="_blank" rel="noreferrer">its CI run</a></dt><dd className="mono">0</dd></div>
      </dl>
      <div className="pitch-multi">
        <button type="button" className="pitch-card" onClick={() => go("Try it live")}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={printoutImageUrl} alt="A printed COBOL listing" width={120} height={80} />
          <span><b>Muse Wonder reads a printed listing</b> and writes the COBOL; GnuCOBOL checks it against the original.</span>
        </button>
        <button type="button" className="pitch-card" onClick={() => go("Try it live")}>
          <span className="pitch-mic" aria-hidden="true"><Mic size={28} /></span>
          <span><b>Ask a program a question out loud</b>; the answer is checked by running the original COBOL.</span>
        </button>
      </div>
      <p className="pitch-models">
        Models write and attack; only the comparison can certify. Meta models only: <strong>Muse Spark</strong>, plus, in some runs, <strong>Muse Spark Open</strong> and <strong>Muse Wonder</strong>.
      </p>
    </section>
  );
}

export default function HomeView({ go }: { go: Go }) {
  const sample = useSampleCheck();
  const [run, setRun] = useState<Run | null>(null);
  useEffect(() => {
    fetchRun(SAMPLE_RUN.id).then(setRun).catch(() => setRun(null));
  }, []);
  useOpenOnHash();
  const final = run?.after?.total ?? SAMPLE_RECORDED.finalHeldOut;
  const [was, now] = catchAmounts(run);
  return (
    <div className="view-content home">
      <Pitch go={go} sample={sample} run={run} />

      <SampleHero go={go} sample={sample} />

      <Numbers go={go} />

      <div className="fold-list">
        <Fold id="certified" title="What “certified” means">
          <ul className="home-list">
            <li>On every input tried, the Java’s records, display output and exit code equal the original’s. Each check is one run of each program on one generated file; the counts are output records compared.</li>
            <li>The original is compiled with <Term tip={GLOSSARY.GnuCOBOL}>GnuCOBOL</Term> 3.2 under IBM’s <Term tip={GLOSSARY["TRUNC(STD)"]}>TRUNC(STD)</Term> and DISPLAY defaults, in <Term tip={GLOSSARY.EBCDIC}>EBCDIC</Term> collating order.</li>
            <li>Where captured mainframe output exists, the mainframe is the judge instead.</li>
          </ul>
        </Fold>
        <Fold id="not-certified" title="What it does not mean">
          <ul className="home-list">
            <li>Equivalence for every possible input: testing cannot show that.</li>
            <li>Equivalence to IBM COBOL where GnuCOBOL differs and no mainframe output was captured.</li>
            <li>Support for <Term tip={GLOSSARY.CICS}>CICS</Term>, <Term tip={GLOSSARY.DB2}>DB2</Term> or <Term tip={GLOSSARY.VSAM}>VSAM</Term> beyond the stated subsets (DB2 and keyed files are verified on stand-ins): those programs are reported, not converted.</li>
          </ul>
          <p className="home-pr">
            <strong>Limits:</strong> &ldquo;certified&rdquo; means matched on the inputs tried, not proven equivalent. Trailing spaces on text lines are not compared. GnuCOBOL is not IBM Enterprise COBOL; SQLite and Berkeley DB stand in for the DB2 and VSAM subsets; the breaker attacks single-file record programs only; optional guard and cross-check steps can be skipped, and a run says so. Synthetic programs only.
            {" "}<strong>For risk and audit teams:</strong> the party that writes the change does not approve it (<a href={`${LINKS.diocle}#for-engineering-risk-and-audit-teams`} target="_blank" rel="noreferrer">what a reviewer can check</a>).
          </p>
          <p className="home-more"><a href={LINKS.certified} target="_blank" rel="noreferrer">Full definition and limits</a></p>
        </Fold>
        <Fold id="measured" title={MEASURED_TITLE} hint={MEASURED_HINT}>
          <MeasuredBody />
        </Fold>
        <Fold id="catch" title={`The ${SAMPLE_RUN.program} catch in full`} hint="A malformed record, not an ordinary transaction">
          <p className="home-pr">Muse Spark designed this input: a cheque returned for insufficient funds whose fee is <span className="mono">␣1000</span>, a space where <span className="mono">PIC 9</span> expects a digit. Malformed data, not an ordinary transaction. Original COBOL on GnuCOBOL charged <span className="mono">{was}</span>; AI-written Java charged <span className="mono">{now}</span>.</p>
          <p className="home-pr">Fixed by the repair agent · matched again on {final.toLocaleString()} output records · a stored run · IBM Enterprise COBOL was not tested and may treat this record differently.</p>
        </Fold>
        <Fold id="how-it-works" title="How it works, step by step">
          <p className="home-pr">For a modernization lead deciding whether to accept AI-written Java for a COBOL batch program.</p>
          <ol className="home-list">
            {PIPELINE.map(([step, who, what]) => <li key={step}><strong>{step}</strong> ({who}): {what}.</li>)}
          </ol>
          <p className="home-pr">Diocle compares output byte for byte, trailing spaces on text lines aside. What differs goes to repair, and the evidence can be re-run.</p>
        </Fold>
        <Evidence go={go} />
        <WhatIsCobol />
        <Fold title="Use it from your editor" hint="Two local installs; not an official Meta product.">
          <p className="home-pr">Two local installs from this repository. Neither is on a marketplace, and neither is an official Meta product.</p>
          <div className="home-columns">
            <div className="editor-col">
              <h3>VS Code (forks such as Cursor should work)</h3>
              <p className="home-pr">Check a COBOL file compiles under GnuCOBOL, then convert and verify it from the editor. Needs Python, GnuCOBOL 3.2 and JDK 21 (run <span className="mono">sh scripts/quickstart.sh --no-key</span> once in the clone to set up the converter, and have <span className="mono">code</span> on your PATH). A conversion uses your own Meta key and asks before it spends. A local build, not yet tested in a clean editor.</p>
              <pre className="mono editor-cmd">{`git clone ${LINKS.diocle}.git
cd Diocle/editors/vscode
npm install && npm run package
code --install-extension diocle-0.1.0.vsix`}</pre>
              <p className="home-pr"><a href={LINKS.vscode} target="_blank" rel="noreferrer">Install notes and settings <ExternalLink size={11} /></a></p>
            </div>
            <div className="editor-col">
              <h3>Muse Code (Meta&apos;s coding agent)</h3>
              <p className="home-pr">A local plugin: Muse Code can analyze COBOL, re-verify a conversion against the original, and read run records through Diocle tools. A real conversion is off unless you turn it on. Tested with Muse Code 1.4.14 on macOS: in five recorded headless runs Muse Code picked and called the Diocle tools and reported their output, including a capped conversion that certified a sample (1027 of 1027 inputs, about two cents) and a refusal outside the repository. The prompts named the tools, and conversion was enabled and capped by the owner.</p>
              <pre className="mono editor-cmd">{`git clone ${LINKS.diocle}.git
cd Diocle
sh editors/muse-code/install.sh
muse plugins approve diocle:mcp_server:diocle`}</pre>
              <p className="home-pr"><a href={LINKS.museCode} target="_blank" rel="noreferrer">Install notes, tools and limits <ExternalLink size={11} /></a></p>
            </div>
          </div>
        </Fold>
        <Fold title="Sample estate" hint="A fictional bank; its programs and data are synthetic.">
          <p className="home-pr">Quillmark Trust &amp; Savings is a fictional bank shipped with Diocle so you can see it work end to end. Its programs and data are synthetic.</p>
          <ul className="home-list home-links">
            <li><a href={LINKS.legacy} target="_blank" rel="noreferrer">quillmark-mainframe</a>: an export of z/OS libraries (COBOL, copybooks, JCL, procedures, DB2, CICS, IMS, EBCDIC extracts).</li>
            <li><a href={LINKS.target} target="_blank" rel="noreferrer">quillmark-java</a>: starts empty; Diocle delivers certified programs as pull requests and its CI re-checks them.</li>
            <li><a href={LINKS.evidence} target="_blank" rel="noreferrer">{CANONICAL.pr}</a>: re-delivers INTACCR, and the repository&apos;s CI re-verifies all six programs under one pinned verifier on {CANONICAL_FRESH_INPUTS.toLocaleString()} fresh output records.</li>
            <li><a href={LINKS.buildLog} target="_blank" rel="noreferrer">Build log</a>: what was built during the hackathon, including the mistakes we found.</li>
          </ul>
          <p className="home-more"><a href={LINKS.diocle} target="_blank" rel="noreferrer">Source on GitHub <ExternalLink size={11} /></a></p>
        </Fold>
      </div>
    </div>
  );
}
