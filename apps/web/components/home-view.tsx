"use client";

import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { LINKS } from "@/lib/config";
import { fetchDeliveries, fetchDelivery, type Delivery } from "@/lib/deliveries";
import { fetchRuns, type RunListItem } from "@/lib/runs";

const usd = (n: number) => `$${n.toFixed(2)}`;

function Evidence() {
  const [delivery, setDelivery] = useState<Delivery | null>(null);
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  useEffect(() => {
    fetchRuns().then(setRuns).catch(() => setRuns([]));
    fetchDeliveries()
      .then((items) => items.find((d) => d.stage === "done" && d.pullRequest))
      .then((d) => (d ? fetchDelivery(d.id) : null))
      .then(setDelivery)
      .catch(() => setDelivery(null));
  }, []);
  const certified = runs?.filter((r) => r.certified).length ?? 0;
  const spent = runs?.reduce((sum, r) => sum + (r.efficiency.estimatedCostUsd ?? 0), 0) ?? 0;
  const ci = delivery?.pullRequest?.checks?.find((c) => c.name === "reverify");
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>Evidence, live from this deployment</h2>
          <p>Counted from the saved runs and the latest delivery, not typed in.</p>
        </div>
      </div>
      <dl className="eff-grid home-evidence">
        <div><dt>Runs certified</dt><dd className="mono">{runs ? `${certified}/${runs.length}` : "…"}</dd></div>
        <div><dt>Latest delivery</dt><dd className="mono">{delivery ? `${delivery.programs.filter((p) => p.status === "certified").length} programs` : "…"}</dd></div>
        <div><dt>CI re-verification</dt><dd className="mono">{ci ? ci.state.toLowerCase() : delivery ? "pending" : "…"}</dd></div>
        <div><dt>Model spend, all runs</dt><dd className="mono">{runs ? usd(spent) : "…"}</dd></div>
      </dl>
      {delivery?.pullRequest && (
        <p className="home-pr">
          Latest pull request: <a href={delivery.pullRequest.url} target="_blank" rel="noreferrer">{delivery.pullRequest.url.replace("https://github.com/", "")}</a>
          {" "}· estimated costs from list prices
        </p>
      )}
    </section>
  );
}

const STEPS: [string, string][] = [
  ["ANALYZE", "Reads a mainframe library export: programs, copybooks, JCL and procedures. Derives every record layout byte by byte and flags behaviour a rewrite must keep."],
  ["CONVERT", "Meta Muse Spark translates each program to Java. A repair agent reads, patches, compiles and re-tests until it matches."],
  ["CHECK", "The original COBOL and the Java run on the same inputs. Every field, byte, display line and return code must agree, including on 1,000 inputs the agent never saw."],
  ["DELIVER", "Each program that passes goes to the target repository as a pull request with a certificate. That repository's CI repeats the check on fresh inputs."],
];

export default function HomeView({ go }: { go: (view: "Delivery" | "Live runs") => void }) {
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
            Banks still run their money through COBOL written decades ago. Converting it is the easy part; knowing the
            new code rounds, truncates and overflows exactly like the old code is the hard part, and today it is done by
            hand, one class at a time. Diocle makes that check automatic, repeatable and inspectable.
          </p>
          <div className="home-actions">
            <button className="button primary" onClick={() => go("Delivery")}>Watch a delivery</button>
            <button className="button secondary" onClick={() => go("Live runs")}>Inspect the runs</button>
            <a className="button secondary" href={LINKS.diocle} target="_blank" rel="noreferrer">Source <ExternalLink size={12} /></a>
          </div>
        </div>
      </section>

      <div className="home-steps">
        {STEPS.map(([title, text], i) => (
          <section key={title} className="panel home-step">
            <div className="panel-heading"><div><h2>{i + 1}. {title}</h2></div></div>
            <p>{text}</p>
          </section>
        ))}
      </div>

      <Evidence />

      <div className="home-columns">
        <section className="panel">
          <div className="panel-heading"><div><h2>What “certified” means</h2></div></div>
          <ul className="home-list">
            <li>On every input tried, the Java’s records, display output and exit code equal the original’s.</li>
            <li>The original is compiled with GnuCOBOL 3.2 under IBM’s TRUNC(STD) and DISPLAY defaults, in EBCDIC collating order.</li>
            <li>Where captured mainframe output exists, the mainframe is the judge instead.</li>
          </ul>
        </section>
        <section className="panel">
          <div className="panel-heading"><div><h2>What it does not mean</h2></div></div>
          <ul className="home-list">
            <li>Equivalence for every possible input: testing cannot show that.</li>
            <li>Equivalence to IBM COBOL where GnuCOBOL differs and no mainframe output was captured.</li>
            <li>Support for CICS, DB2 or VSAM updates: those programs are reported, not converted.</li>
          </ul>
          <p className="home-more"><a href={LINKS.certified} target="_blank" rel="noreferrer">Full definition and limits</a></p>
        </section>
      </div>

      <section className="panel">
        <div className="panel-heading"><div><h2>The demo estate</h2><p>A fictional bank, Quillmark Trust &amp; Savings. All programs and data are synthetic.</p></div></div>
        <ul className="home-list home-links">
          <li><a href={LINKS.legacy} target="_blank" rel="noreferrer">quillmark-mainframe</a>: an export of z/OS libraries (COBOL, copybooks, JCL, procedures, DB2, CICS, IMS, EBCDIC extracts).</li>
          <li><a href={LINKS.target} target="_blank" rel="noreferrer">quillmark-java</a>: starts empty; Diocle delivers certified programs as pull requests and its CI re-checks them.</li>
          <li><a href={LINKS.evidence} target="_blank" rel="noreferrer">quillmark-modern pull request #3</a>: six programs, re-verified by GitHub CI on 6,714 fresh inputs.</li>
          <li><a href={LINKS.buildLog} target="_blank" rel="noreferrer">Build log</a>: what was built during the hackathon, including the mistakes we found.</li>
        </ul>
      </section>
    </div>
  );
}
