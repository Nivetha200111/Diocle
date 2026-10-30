"use client";

// Bug of the day: real catches from the engine's stored runs (see lib/bugs.ts). Read-only; no model call.
import { useEffect, useState } from "react";
import { Brand } from "./ui";
import { fetchRun, fetchRuns, type Run } from "@/lib/runs";
import { CARDS, MUTANTS, REPO_ONLY, fallbackCards, resolveCards, roleLabel, type Resolved } from "@/lib/bugs";

const usd = (n: number) => `$${n.toFixed(n < 1 ? 4 : 2)}`;

function Card({ r }: { r: Resolved }) {
  const { spec, catch: c, live } = r;
  const external = spec.source.href.startsWith("http");
  return (
    <article className="bug-card" aria-labelledby={`bug-${spec.key}`}>
      <header>
        <h2 id={`bug-${spec.key}`}>{spec.title}</h2>
        <span className={`bug-tag ${live ? "is-live" : "is-repo"}`}>{live ? "checked against the live run record" : "from the repository's recorded results, not live"}</span>
      </header>
      <p className="bug-prog"><strong>{spec.program}</strong>, field <code>{c.field}</code></p>
      <div className="bug-vs">
        <div><span>The COBOL produced</span><code>{c.original}</code></div>
        <div><span>The AI-written Java produced</span><code>{c.java}</code></div>
      </div>
      <dl className="bug-meta">
        <div><dt>Caught by</dt><dd>{roleLabel(c.role)}</dd></div>
        <div><dt>Model</dt><dd>{c.model}</dd></div>
        <div><dt>When</dt><dd>{c.round}</dd></div>
        <div><dt>Cost of the run</dt><dd>{c.costUsd === null ? "not recorded" : <>{usd(c.costUsd)}{c.costNote ? <small> ({c.costNote})</small> : null}</>}</dd></div>
        <div><dt>Run</dt><dd>{spec.runId ? <a href={`/runs#run=${encodeURIComponent(spec.runId)}`}>{spec.runId}</a> : "not on the live engine"}</dd></div>
      </dl>
      <p className="bug-why"><strong>Why this matters.</strong> {spec.why}</p>
      {spec.caveat && <p className="bug-note">{spec.caveat}</p>}
      <p className="bug-src">Source: {external ? <a href={spec.source.href} target="_blank" rel="noreferrer">{spec.source.label}</a> : <a href={spec.source.href}>{spec.source.label}</a>}</p>
    </article>
  );
}

type State = { phase: "loading" } | { phase: "failed" } | { phase: "ok"; shown: Resolved[]; unconfirmed: number };

export default function BugsView() {
  const [state, setState] = useState<State>({ phase: "loading" });
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const list = await fetchRuns();
        const ids = [...new Set(CARDS.map((c) => c.runId).filter((id): id is string => !!id && list.some((i) => i.id === id)))];
        const got = await Promise.allSettled(ids.map((id) => fetchRun(id)));
        const runs: Record<string, Run> = {};
        for (const g of got) if (g.status === "fulfilled") runs[g.value.id] = g.value;
        if (alive) setState({ phase: "ok", ...resolveCards(runs) });
      } catch {
        if (alive) setState({ phase: "failed" });
      }
    })();
    return () => { alive = false; };
  }, []);

  return (
    <div className="mc-page">
      <header className="mc-top">
        <a href="/" aria-label="Diocle home"><Brand /></a>
        <nav aria-label="Main navigation" className="mc-nav">
          <a href="/">Home</a>
          <a href="/runs">Live runs</a>
          <a href="/evidence">Evidence</a>
          <a href="/mission">Mission control</a>
          <a href="/bugs" aria-current="page">Bug of the day</a>
        </nav>
      </header>
      <main className="mc-main">
        <h1>Bug of the day</h1>
        <p className="mc-lede">
          Real mistakes in AI-written Java that the original COBOL, run side by side, exposed. Each card is read from a stored run on the
          Diocle engine; a card that the run record no longer confirms is not shown. These were caught on the inputs tried, which is not
          a proof that no other difference exists.
        </p>
        {state.phase === "loading" && <section className="panel mc-empty" role="status"><p>Reading the stored runs from the engine.</p></section>}
        {state.phase === "failed" && (
          <section className="panel mc-empty" role="alert">
            <h2>The engine could not be reached</h2>
            <p>The cards below are from the repository&apos;s recorded results, not read live, so the links to runs may not open until the engine is back.</p>
          </section>
        )}
        {state.phase === "ok" && state.shown.length === 0 && (
          <section className="panel mc-empty" role="alert">
            <h2>No catch could be confirmed</h2>
            <p>The engine answered, but none of its run records contains the catches listed in the repository. Nothing is shown in their place.</p>
          </section>
        )}
        {state.phase === "ok" && state.unconfirmed > 0 && state.shown.length > 0 && (
          <p className="bug-hidden">{state.unconfirmed} of {CARDS.length} catches are hidden because the engine&apos;s run records did not confirm them.</p>
        )}
        <section className="bug-grid" aria-label="Catches from stored runs">
          {state.phase === "ok" && state.shown.map((r) => <Card key={r.spec.key} r={r} />)}
          {state.phase === "failed" && fallbackCards().map((r) => <Card key={r.spec.key} r={r} />)}
        </section>

        <h2 className="bug-h2">Earlier catches recorded in the repository</h2>
        <p className="mc-lede">Not read from a live run record: these come from the repository&apos;s documents and are labelled so.</p>
        <section className="bug-grid" aria-label="Catches recorded in the repository">
          {REPO_ONLY.map((spec) => <Card key={spec.key} r={{ spec, catch: spec.repo, live: false }} />)}
        </section>

        <h2 className="bug-h2">How we test the verifier</h2>
        <section className="panel bug-mutants">
          <p>These are not catches of a model. They are deliberately wrong programs written inside our unit tests, to prove that the verifier fails when it should. The tests run GnuCOBOL and Java for real.</p>
          <ul>
            {MUTANTS.map((m) => (
              <li key={m.test}><strong>{m.title}.</strong> {m.how} <code>{m.test}</code></li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
