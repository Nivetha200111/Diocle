"use client";

import { LINKS } from "@/lib/config";
import "@/app/banks/banks.css";

const DETAILS = `${LINKS.diocle}/blob/main/docs/DETAILS.md`;

// Each row restates README.md "For engineering, risk and audit teams" or docs/DETAILS.md, and keeps the qualifier that makes it true.
const ROWS: { what: string; detail: string; link: string; label: string }[] = [
  {
    what: "An equivalence report in the pull request",
    detail: "One per program, pinning every input to the result. The example has six synthetic programs.",
    link: LINKS.evidence,
    label: "See one",
  },
  {
    what: "CI re-running on fresh inputs, in your repository",
    detail: "A new seed each run. It shares the verifier's assumptions, and a flat text record's generated inputs do not change with the seed.",
    link: LINKS.evidenceCi,
    label: "An example run",
  },
  {
    what: "A model never certifies",
    detail: "Models write and attack. Only a deterministic comparison with the original can certify.",
    link: LINKS.certified,
    label: "What certified means",
  },
  {
    what: "The writer is not the approver",
    detail: "The party that writes the change does not approve it. It narrows what a person must review; it does not replace that review.",
    link: `${LINKS.diocle}#for-engineering-risk-and-audit-teams`,
    label: "What a reviewer can check",
  },
  {
    what: "Refusals per program, with reasons",
    detail: "What it cannot verify, such as EXEC CICS or dynamic CALL, is refused with a reason. Local and admin convert-anyway output is labelled unverified, never certified.",
    link: `${DETAILS}#not-supported-yet`,
    label: "Not supported yet",
  },
  {
    what: "A sandbox with no credentials and no network",
    detail: "On the public engine, the code compiles and runs there; run locally, it runs on your machine. Model calls go to the host you configure.",
    link: `${DETAILS}#which-model-does-what`,
    label: "Which model does what",
  },
  {
    what: "Hard cost caps",
    detail: "Every model loop has hard call caps. Public buttons, imports, the quickstart and escalation also have dollar caps.",
    link: "/try",
    label: "See the caps on Try it live",
  },
  {
    what: "Private mode on open weights",
    detail: "The agents can run on Muse Spark Open through partner inference, on Fireworks or Baseten. That is the partner's hardware, not yours; running the weights on your own hardware is untested. Optional and thinly tested.",
    link: "/evidence#private-mode",
    label: "One private-mode result",
  },
  {
    what: "Every run lists its checks and skips",
    detail: "Run pages and new certificates list which checks ran and which were skipped, plus stated stand-ins. A skipped check is not a pass.",
    link: "/runs",
    label: "Run history",
  },
];

const external = (href: string) => (href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {});

export default function BanksView() {
  return (
    <>
      <section className="panel banks-value">
        <p>Evidence a reviewer can re-run, instead of trusting a model&apos;s word.</p>
      </section>

      <section className="panel" aria-labelledby="banks-get">
        <div className="panel-heading"><div><h2 id="banks-get">What your teams get</h2></div></div>
        <ul className="banks-rows">
          {ROWS.map((r) => (
            <li key={r.what}>
              <strong>{r.what}</strong>
              <span>{r.detail} <a href={r.link} {...external(r.link)}>{r.label}</a></span>
            </li>
          ))}
        </ul>
      </section>

      <section className="panel" aria-labelledby="banks-pilot">
        <div className="panel-heading"><div><h2 id="banks-pilot">A first pilot</h2></div></div>
        <p className="banks-note">What a pilot would look like. This has not happened.</p>
        <ol className="banks-list">
          <li>Start on one low-risk batch program.</li>
          <li>On z/OS, the bank runs that program itself and captures its mainframe output.</li>
          <li>Diocle replays that captured output as the judge of the Java, in place of GnuCOBOL. The replay path exists, but no real mainframe output has been tested yet.</li>
          <li>A person still reviews the code and accepts it on the real runtime.</li>
        </ol>
      </section>

      <section className="panel" aria-labelledby="banks-not">
        <div className="panel-heading"><div><h2 id="banks-not">Not there yet</h2></div></div>
        <ul className="banks-list">
          <li>No bank has used it.</li>
          <li>No security audit or compliance certification.</li>
          <li>Results are under GnuCOBOL, not IBM Enterprise COBOL.</li>
          <li>Batch only; CICS is refused.</li>
          <li>Verified on the inputs tried, not a formal proof.</li>
          <li>No outside user has evaluated it yet.</li>
        </ul>
        <p className="banks-more"><a href={`${DETAILS}#not-supported-yet`} target="_blank" rel="noreferrer">Everything not supported yet</a></p>
      </section>
    </>
  );
}
