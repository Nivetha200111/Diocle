"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { CANONICAL, CANONICAL_FRESH_INPUTS, GLOSSARY, LINKS, MODELS, SAMPLE_RUN } from "@/lib/config";
import { fetchRuns, isInterrupted, type RunListItem } from "@/lib/runs";
import { Skeleton, Term } from "./ui";

const usd = (n: number) => `$${n.toFixed(2)}`;
const runLink = (id: string) => `#run=${encodeURIComponent(id)}`;

// Proof in one place. The canonical delivery's numbers are cited from its GitHub Actions run; the engine's own
// counts are read live from the API.
export default function EvidenceView({ openRun }: { openRun: (id: string) => void }) {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  useEffect(() => {
    fetchRuns().then(setRuns).catch(() => setRuns([]));
  }, []);
  const kept = runs ?? [];
  const certified = kept.filter((r) => r.certified).length;
  const interrupted = kept.filter((r) => isInterrupted(r)).length;
  const spend = kept.reduce((n, r) => n + (r.efficiency.estimatedCostUsd ?? 0), 0);
  const privateRun = runs?.find((r) => r.model === MODELS.open && r.certified);
  const open = (id: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    openRun(id);
  };
  return (
    <>
      <section className="panel evidence-summary">
        <div className="panel-heading">
          <div>
            <h2>Canonical delivery: {CANONICAL.pr}</h2>
            <p>Six COBOL programs from quillmark-legacy, certified under one pinned verifier and delivered as one pull request.</p>
          </div>
        </div>
        <dl className="eff-grid home-evidence">
          <div><dt>Programs</dt><dd className="mono">{CANONICAL.programs.length}</dd></div>
          <div><dt>Fresh inputs in CI</dt><dd className="mono">{CANONICAL_FRESH_INPUTS.toLocaleString()}</dd></div>
          <div><dt>Differences</dt><dd className="mono">{CANONICAL.differences}</dd></div>
          <div><dt>Model spend (est.)</dt><dd className="mono">≈{usd(CANONICAL.modelSpendUsd)}</dd></div>
        </dl>
        <div className="table-scroll evidence-table">
          <table className="data-table">
            <thead><tr><th>Program</th><th>Inputs re-checked by the target repository&apos;s CI</th><th>Result</th></tr></thead>
            <tbody>
              {CANONICAL.programs.map((p) => (
                <tr key={p.name}><td className="mono">{p.name}</td><td className="mono">{p.ci.toLocaleString()}/{p.ci.toLocaleString()}</td><td>match, stdout matches</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="home-pr">
          <a href={LINKS.evidence} target="_blank" rel="noreferrer">Pull request <ExternalLink size={11} /></a>
          {" · "}<a href={LINKS.evidenceCi} target="_blank" rel="noreferrer">CI run <ExternalLink size={11} /></a>
          {" · "}<a href={LINKS.evidenceDoc} target="_blank" rel="noreferrer">docs/EVIDENCE.md <ExternalLink size={11} /></a>
          {" · "}CI re-runs both programs from a seed Diocle never used. Costs are estimates from list prices.
        </p>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>The breaker agent found what 1,000 inputs missed</h2>
            <p>{SAMPLE_RUN.program}, an unseen program from the frozen evaluation.</p>
          </div>
        </div>
        <ol className="home-list">
          <li>Muse Spark translated it; the Java passed 1,004 of 1,004 <Term tip={GLOSSARY["held-out"]}>held-out</Term> inputs.</li>
          <li>The breaker agent (also Muse Spark) designed 24 inputs. Two broke it. First, the return fee for a cheque bounced for insufficient funds (NSF; the base fee is doubled, and the unit is not stated in the COBOL). The COBOL charged <span className="mono">20.00</span>; the AI-written Java charged <span className="mono">0.00</span>. Second, a debit of <span className="mono">-121.23</span> in COBOL vs <span className="mono">0.00</span> in Java.</li>
          <li>The repair agent fixed both; the Java re-certified on 1,006 fresh held-out inputs.</li>
          <li>Both inputs carry malformed numeric data, so this shows agreement with GnuCOBOL&apos;s handling of bad data, not proven IBM behaviour.</li>
        </ol>
        <p className="home-more"><a href={runLink(SAMPLE_RUN.id)} onClick={open(SAMPLE_RUN.id)}>Open the run, with its trace and a re-verify button</a></p>
      </section>

      <div className="home-columns">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Unseen programs (frozen evaluation)</h2>
              <p>Four programs written after the converter was frozen.</p>
            </div>
          </div>
          <ul className="home-list">
            <li><strong>eval-freeze-1: 2 of 4 certified.</strong> Both failures turned out to be a verifier bug: it rejected aggregation and fan-out programs.</li>
            <li><strong>eval-freeze-2: 4 of 4 certified, about $0.11</strong>, with the corrected verifier and fix memory off; each program also passed five fresh seeds.</li>
            <li>Both runs are published, failures included.</li>
          </ul>
          <p className="home-more"><a href={LINKS.evaluation} target="_blank" rel="noreferrer">docs/EVALUATION.md</a></p>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Private mode on open weights</h2>
              <p>The same agents on Muse Spark Open, served by Fireworks.</p>
            </div>
          </div>
          <ul className="home-list">
            <li>Model: <span className="mono">{MODELS.open}</span>. Open weights can run on infrastructure you control.</li>
            <li>INTACCR translated from scratch and certified first time on 1,027 held-out inputs; the breaker designed 21 inputs and none broke it.</li>
          </ul>
          {privateRun && <p className="home-more"><a href={runLink(privateRun.id)} onClick={open(privateRun.id)}>Open the private-mode run</a></p>}
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>A public course repository, imported by a visitor</h2>
            <p>Not our code: the Open Mainframe Project&apos;s COBOL course, imported with the public import (delivery-20261030-022234).</p>
          </div>
        </div>
        <ul className="home-list">
          <li><strong>2 certified, 1 not, 21 skipped, under a cent of model spend ($0.0074).</strong> The programs are tiny teaching programs (13 to 23 lines) that print to the screen, so each is checked on one run of its output, not on a thousand inputs.</li>
          <li><strong>CBL0013 and CBL0014 certified</strong>: the Java printed exactly what the COBOL printed, and the exit code matched.</li>
          <li><strong>CBL0015 not certified, correctly:</strong> the program loops forever (<span className="mono">PERFORM UNTIL ALWAYS-TRUE = &apos;N&apos;</span>, and nothing sets it), so GnuCOBOL never finishes it. The engine reports this as a verifier failure; saying &quot;the program never ends&quot; is on the to-do list.</li>
          <li><strong>11 skipped before any model spend:</strong> their originals do not compile under GnuCOBOL (<span className="mono">-std=ibm</span>), so there is nothing to compare against. The other 10 were skipped by the visitor limit of three programs.</li>
        </ul>
        <p className="home-pr">
          Source: <a href="https://github.com/openmainframeproject/cobol-programming-course" target="_blank" rel="noreferrer">openmainframeproject/cobol-programming-course</a>,
          licensed <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a> by its authors
          (the Open Mainframe Project community). We converted the programs to Java; the originals are unchanged in that repository.
        </p>
      </section>

      {runs === null ? <Skeleton rows={3} label="Loading this engine's runs" /> : (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Everything this engine has kept, live</h2>
              <p>Counted from the API just now, not typed in.</p>
            </div>
          </div>
          <dl className="eff-grid home-evidence">
            <div><dt>Runs certified</dt><dd className="mono">{certified}/{kept.length}</dd></div>
            <div><dt>Model spend, all runs (est.)</dt><dd className="mono">{usd(spend)}</dd></div>
          </dl>
          <p className="home-pr">
            {certified}/{kept.length} counts every run this engine has kept, including failed attempts (two of them
            evaluation runs the old verifier rejected){interrupted ? `, ${interrupted} interrupted by an engine restart` : ""} and
            superseded runs. The {CANONICAL.programs.length}/{CANONICAL.programs.length} above is one delivery.
            Every certified run (except visitor imports) can be re-verified by anyone in Live runs.
          </p>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading"><div><h2>Corrections we published</h2></div></div>
        <ul className="home-list">
          <li>Oct 28: the comparator compared numbers by value, so <span className="mono">+00</span> equalled <span className="mono">-00</span>. Fixed to byte-exact; re-checking found one INTACCR (quillmark-modern#3) that should not have passed. It was re-delivered in {CANONICAL.pr}, where the repair agent fixed the sign of zero itself.</li>
          <li>The full list, with what we got wrong: <a href={LINKS.buildLog} target="_blank" rel="noreferrer">docs/BUILD_LOG.md</a>.</li>
        </ul>
      </section>
    </>
  );
}
