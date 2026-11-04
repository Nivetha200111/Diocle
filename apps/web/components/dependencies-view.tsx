"use client";

import { useMemo, useState } from "react";
import { ExternalLink } from "lucide-react";
import data from "@/lib/dependency-trees.json";
import { buildForest, dependentsOf, impactLine, type TreeNode } from "@/lib/dependency-impact";
import { useOpenOnHash } from "./ui";
import "@/app/dependencies/dependencies.css";

type Attempt = (typeof data.trees)[number]["attempts"][number];
type Tree = (typeof data.trees)[number];

const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const repoName = (url: string) => url.replace("https://github.com/", "");

// What the edges of a tree are, in the words the analyzer's report uses.
function linkWords(kinds: string[]) {
  const words: Record<string, string> = { call: "CALLs", copy: "COPYs", job: "JCL job to program" };
  return kinds.map((k) => words[k] ?? k).join(" and ");
}

function selfLoopWords(tree: Tree) {
  return tree.kinds.includes("job") ? "a JCL job and a program with this one name" : "the report has it calling itself";
}

function Node({ node, tree, selected, dependents, pick }: {
  node: TreeNode;
  tree: Tree;
  selected: string | null;
  dependents: Set<string>;
  pick: (name: string) => void;
}) {
  const isSelected = selected === node.name;
  const isDependent = dependents.has(node.name);
  return (
    <li>
      <button
        type="button"
        className={`tree-node ${isSelected ? "is-selected" : ""} ${isDependent ? "is-dependent" : ""}`}
        aria-pressed={isSelected}
        onClick={() => pick(node.name)}
      >
        <span className="mono tree-name">{node.name}</span>
        {isSelected && <span className="tree-tag">selected</span>}
        {isDependent && <span className="tree-tag">depends on it</span>}
      </button>
      {node.selfLoop && <span className="tree-aside">links to itself: {selfLoopWords(tree)}</span>}
      {node.shownAbove && <span className="tree-aside">links shown above</span>}
      {node.children.length > 0 && (
        <ul>
          {node.children.map((c, i) => <Node key={`${c.name}-${i}`} node={c} tree={tree} selected={selected} dependents={dependents} pick={pick} />)}
        </ul>
      )}
    </li>
  );
}

// The analyzer's tree, always exact: it is drawn here from the report's edges and no model is involved.
function AnalyzerTree({ tree }: { tree: Tree }) {
  const forest = useMemo(() => buildForest(tree.edges), [tree.edges]);
  const [selected, setSelected] = useState<string | null>(null);
  const dependents = useMemo(() => new Set(selected ? dependentsOf(tree.edges, selected) : []), [tree.edges, selected]);
  return (
    <div className="tree-analyzer">
      <h3>From the analyzer&apos;s report</h3>
      <div className="tree-impact">
        <p role="status">{selected ? impactLine(tree.edges, selected) : "Select a name to see what depends on it."}</p>
        {selected && <button type="button" className="link-button" onClick={() => setSelected(null)}>Clear</button>}
      </div>
      <ul className="tree-list">
        {forest.map((root, i) => (
          <Node key={`${root.name}-${i}`} node={root} tree={tree} selected={selected} dependents={dependents}
            pick={(name) => setSelected((now) => (now === name ? null : name))} />
        ))}
      </ul>
    </div>
  );
}

function readBackWords(a: Attempt) {
  return `read back with ${count(a.missingEdges, "link")} missing, ${count(a.inventedEdges, "link")} extra, ${count(a.missingNodes, "box", "boxes")} missing, ${count(a.inventedNodes, "box", "boxes")} extra`;
}

// Drawings that did not pass stay one click away and carry that label on the picture, in its caption and in its alt text.
function FailedDrawings({ tree, failed }: { tree: Tree; failed: Attempt[] }) {
  if (!failed.length) return null;
  return (
    <details className="inline-more tree-failed">
      <summary>{failed.length === 1 ? `The drawing that did not pass, attempt ${failed[0].attempt}` : `The ${failed.length} drawings that did not pass`}</summary>
      <p>Did not pass the check, so not shown as checked. The check can reject a good drawing. The analyzer&apos;s tree is the source of truth.</p>
      <div className="tree-failed-grid">
        {failed.map((a) => (
          <figure key={a.attempt}>
            <div className="tree-failed-frame">
              <span className="tree-failed-tag">Did not pass the check</span>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/trees/${a.image}`} alt={`Drawing, attempt ${a.attempt}, of ${tree.title}. It did not pass the check.`} width={1600} height={1600} loading="lazy" />
            </div>
            <figcaption>Attempt {a.attempt}, did not pass: {readBackWords(a)}.</figcaption>
          </figure>
        ))}
      </div>
    </details>
  );
}

function Drawing({ tree }: { tree: Tree }) {
  const [broken, setBroken] = useState(false);
  const failed = tree.attempts.filter((a) => !a.match);
  if (!tree.image) {
    return (
      <div className="tree-drawing-failed">
        <p className="tree-check-failed">
          <strong>{tree.part ? "Drawings of this part did not pass the check" : "Whole-repository drawings did not pass the check"}</strong>: {failed.length} of {tree.attempts.length} attempts. The tree here is the analyzer&apos;s.
        </p>
        <FailedDrawings tree={tree} failed={failed} />
      </div>
    );
  }
  const passed = tree.attempts.find((a) => a.match);
  return (
    <div className="tree-drawing">
      <h3>Drawn by Muse Image, then checked</h3>
      {broken ? <p className="dlv-error">The drawing could not be loaded.</p> : (
        <a href={`/trees/${tree.image}`} target="_blank" rel="noreferrer">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`/trees/${tree.image}`} alt={`Muse Image's drawing of ${tree.title}. It passed the check.`} width={1600} height={1600} loading="lazy" onError={() => setBroken(true)} />
        </a>
      )}
      <p className="tree-check">Drawn by Muse Image. Muse Wonder read it back without seeing the graph, and code compared that with the analyzer: exact match on attempt {passed?.attempt}.</p>
      <FailedDrawings tree={tree} failed={failed} />
    </div>
  );
}

function TreeCard({ tree }: { tree: Tree }) {
  const short = tree.commit.slice(0, 7);
  return (
    <section className={`panel tree-card ${tree.image ? "has-drawing" : "no-drawing"}`} id={tree.slug}>
      <div className="panel-heading tree-head"><div>
        <h2>{tree.title}</h2>
        <p>
          <a href={tree.repository} target="_blank" rel="noreferrer">{repoName(tree.repository)} <ExternalLink size={11} /></a>
          {" at "}<a className="mono" href={`${tree.repository}/tree/${tree.commit}`} target="_blank" rel="noreferrer">{short}</a>
          {" · "}{linkWords(tree.kinds)}{" · "}{count(tree.edges.length, "link")}
        </p>
        {tree.note && <p>{tree.note}</p>}
      </div></div>
      <div className="tree-body">
        <AnalyzerTree tree={tree} />
        <Drawing tree={tree} />
      </div>
    </section>
  );
}

export default function DependenciesView() {
  useOpenOnHash();
  // The small trees that passed lead; the whole repositories, whose drawings did not pass, follow with the analyzer's tree.
  const parts = data.trees.filter((t) => t.part);
  const small = data.trees.filter((t) => !t.part && t.verified);
  const whole = data.trees.filter((t) => !t.part && !t.verified);
  return (
    <>
      <section className="panel tree-intro">
        <p>Each tree comes from the analyzer&apos;s report, with no model involved. A drawing shows here only if Muse Wonder reads it back, without seeing the graph, and it matches the analyzer exactly. This can reject a good drawing. The analyzer&apos;s tree is the source of truth.</p>
        <p>Select a name to see what depends on it in the analyzer&apos;s report. That covers only the links the analyzer found (CALLs, COPY and JCL as drawn). It does not predict what would break at run time: dynamic CALLs and refused programs may be missing.</p>
      </section>
      {[...parts, ...small].map((t) => <TreeCard key={t.slug} tree={t} />)}
      {whole.length > 0 && <h2 className="tree-section">Whole repositories</h2>}
      {whole.map((t) => <TreeCard key={t.slug} tree={t} />)}
    </>
  );
}
