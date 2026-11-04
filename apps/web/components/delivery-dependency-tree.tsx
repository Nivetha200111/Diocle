"use client";

import { memo, useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import { dependencyDrawingUrl, type DependencyDrawing, type DependencyTree } from "@/lib/deliveries";
import type { Edge } from "@/lib/dependency-impact";
import { GroupedTree, selfLoopWords } from "./dependency-tree";

const repoName = (url: string) => url.replace("https://github.com/", "");
const KIND_WORDS: Record<string, [string, string]> = { copy: ["COPY link", "COPY links"], call: ["CALL link", "CALL links"], job: ["JCL link", "JCL links"] };

function counts(tree: DependencyTree) {
  const kinds = (["copy", "call", "job"] as const).map((k) => [k, tree.edges.filter((e) => e.kind === k).length] as const).filter(([, n]) => n > 0);
  return kinds.map(([k, n]) => `${n.toLocaleString()} ${KIND_WORDS[k][n === 1 ? 0 : 1]}`).join(", ");
}

// One line in every case but a pass: a drawing that did not pass was not kept, and an off or capped feature is not news.
function Drawing({ id, drawing }: { id: string; drawing?: DependencyDrawing | null }) {
  const [broken, setBroken] = useState(false);
  if (drawing?.status === "passed" && drawing.verified) {
    const url = dependencyDrawingUrl(id);
    return (
      <div className="tree-drawing dep-drawing">
        {broken ? <p className="dlv-error">The drawing could not be loaded.</p> : (
          <a href={url} target="_blank" rel="noreferrer">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={url} alt={`Muse Image's drawing of the links of ${drawing.part?.program ?? "one program"}. It passed the check.`} width={1024} height={1024} loading="lazy" onError={() => setBroken(true)} />
          </a>
        )}
        <p className="tree-check">Drawn by Muse Image. Muse Wonder read it back without seeing the graph, and code compared that with the analyzer: exact match on attempt {drawing.passedOnAttempt}.</p>
        {drawing.part && <p>It shows one small part: the {drawing.part.edges.length} links of <span className="mono">{drawing.part.program}</span>. The analyzer&apos;s tree below is the source of truth.</p>}
      </div>
    );
  }
  const line = drawing?.status === "failed" ? "Muse Image's drawing did not pass the check, so only the analyzer's tree is shown. This can reject a good drawing."
    : drawing?.status === "drawing" ? "Muse Image is drawing one small part of this tree. It appears here only if it passes the check."
    : "No Muse Image drawing for this delivery, so only the analyzer's tree is shown.";
  return <p className="dep-drawing-line">{line}</p>;
}

function Section({ id, repository, commit, tree, drawing, running, analyzing }: {
  id: string;
  drawing?: DependencyDrawing | null;
  repository: string;
  commit: string | null;
  tree?: DependencyTree | null;
  running: boolean;
  analyzing: boolean;
}) {
  const pairs = useMemo<Edge[]>(() => (tree?.edges ?? []).map((e) => [e.from, e.to]), [tree]);
  const loops = useMemo(() => {
    const kinds = new Map<string, string[]>();
    for (const e of tree?.edges ?? []) if (e.from === e.to) kinds.set(e.from, [...(kinds.get(e.from) ?? []), e.kind]);
    return kinds;
  }, [tree]);
  if (!tree) {
    return (
      <section className="panel dep-section">
        <div className="panel-heading"><div>
          <h2>Dependency tree</h2>
          <p>{analyzing && running
            ? "The tree appears here as soon as the analyzer finishes."
            : "No dependency tree is recorded for this delivery: it predates the tree, or stopped before the analyzer finished."}</p>
        </div></div>
      </section>
    );
  }
  const onGithub = repository.startsWith("https://github.com/");
  const commitOk = !!commit && /^[0-9a-f]{7,40}$/.test(commit);
  return (
    <section className="panel dep-section" id="dependency-tree">
      <div className="panel-heading"><div>
        <h2>Dependency tree</h2>
        <p>
          {onGithub ? <a href={repository} target="_blank" rel="noreferrer">{repoName(repository)} <ExternalLink size={11} /></a> : repository}
          {commit && <>{" at "}{onGithub && commitOk
            ? <a className="mono" href={`${repository}/tree/${commit}`} target="_blank" rel="noreferrer">{commit.slice(0, 7)}</a>
            : <span className="mono">{commit.slice(0, 7)}</span>}</>}
          {tree.total > 0 && <>{" · "}{counts(tree)}</>}
        </p>
        <p>From the analyzer&apos;s report, with no model involved. Impact covers only the links in that report, not everything that could break at run time: dynamic CALLs and refused programs may be missing.</p>
      </div></div>
      {tree.truncated && (
        <p className="dep-note">Showing the first {tree.edges.length.toLocaleString()} of {tree.total.toLocaleString()} links. The rest are not recorded here, so impact can miss names in this repository.</p>
      )}
      <Drawing id={id} drawing={drawing} />
      {tree.edges.length === 0
        ? <p className="dep-empty">The analyzer found no CALL, COPY or JCL links in this repository.</p>
        : <GroupedTree edges={pairs} loopWords={(name) => selfLoopWords(loops.get(name) ?? [])} />}
    </section>
  );
}

// The page re-renders every second for its clock and polls the record every two: the same recorded tree must not rebuild.
export const DeliveryDependencyTree = memo(Section, (a, b) => a.id === b.id && JSON.stringify(a.drawing) === JSON.stringify(b.drawing) && a.repository === b.repository && a.commit === b.commit
  && a.tree?.total === b.tree?.total && a.tree?.edges.length === b.tree?.edges.length && a.running === b.running && a.analyzing === b.analyzing);
