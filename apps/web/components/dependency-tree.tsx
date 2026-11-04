"use client";

import { useMemo, useState } from "react";
import { buildForest, dependentsOf, groupsOf, impactLine, reachableEdges, type Edge, type TreeNode } from "@/lib/dependency-impact";
import "@/app/dependencies/dependencies.css";

// The analyzer's tree, always exact: it is drawn here from the report's edges and no model is involved. Names come from the
// analyzed repository, so they are only ever rendered as text.

export function selfLoopWords(kinds: string[]) {
  return kinds.includes("job") ? "a JCL job and a program with this one name" : "the report has it calling itself";
}

function Branch({ node, loopWords, selected, dependents, pick }: {
  node: TreeNode;
  loopWords: (name: string) => string;
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
      {node.selfLoop && <span className="tree-aside">links to itself: {loopWords(node.name)}</span>}
      {node.shownAbove && <span className="tree-aside">links shown above</span>}
      {node.children.length > 0 && (
        <ul>
          {node.children.map((c, i) => <Branch key={`${c.name}-${i}`} node={c} loopWords={loopWords} selected={selected} dependents={dependents} pick={pick} />)}
        </ul>
      )}
    </li>
  );
}

function Impact({ edges, selected, clear }: { edges: readonly Edge[]; selected: string | null; clear: () => void }) {
  return (
    <div className="tree-impact">
      <p role="status">{selected ? impactLine(edges, selected) : "Select a name to see what depends on it."}</p>
      {selected && <button type="button" className="link-button" onClick={clear}>Clear</button>}
    </div>
  );
}

// One whole graph, every name in view: the small recorded trees on the Dependency tree page.
export function AnalyzerTree({ edges, loopWords }: { edges: readonly Edge[]; loopWords: (name: string) => string }) {
  const forest = useMemo(() => buildForest(edges), [edges]);
  const [selected, setSelected] = useState<string | null>(null);
  const dependents = useMemo(() => new Set(selected ? dependentsOf(edges, selected) : []), [edges, selected]);
  return (
    <div className="tree-analyzer">
      <h3>From the analyzer&apos;s report</h3>
      <Impact edges={edges} selected={selected} clear={() => setSelected(null)} />
      <ul className="tree-list">
        {forest.map((root, i) => (
          <Branch key={`${root.name}-${i}`} node={root} loopWords={loopWords} selected={selected} dependents={dependents}
            pick={(name) => setSelected((now) => (now === name ? null : name))} />
        ))}
      </ul>
    </div>
  );
}

function Group({ edges, name, links, loopWords, selected, dependents, pick, startOpen }: {
  edges: readonly Edge[];
  name: string;
  links: number;
  loopWords: (name: string) => string;
  selected: string | null;
  dependents: Set<string>;
  pick: (name: string) => void;
  startOpen: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  // Built only while open, so a repository with hundreds of links costs one line per group until someone looks inside.
  const forest = useMemo(() => (open ? buildForest(reachableEdges(edges, name)) : []), [open, edges, name]);
  return (
    <details className="dep-group" open={startOpen} onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>
        <span className="mono tree-name">{name}</span> <span className="dep-count">{links === 1 ? "1 link" : `${links} links`}</span>
        {selected === name && <span className="tree-tag"> selected</span>}
        {dependents.has(name) && <span className="tree-tag"> depends on it</span>}
      </summary>
      {open && (
        <ul className="tree-list">
          {forest.map((root, i) => <Branch key={`${root.name}-${i}`} node={root} loopWords={loopWords} selected={selected} dependents={dependents} pick={pick} />)}
        </ul>
      )}
    </details>
  );
}

// A whole repository: one collapsed group per program or JCL job, with one selection and one impact line across them all.
export function GroupedTree({ edges, loopWords }: { edges: readonly Edge[]; loopWords: (name: string) => string }) {
  const groups = useMemo(() => groupsOf(edges), [edges]);
  const [selected, setSelected] = useState<string | null>(null);
  const dependents = useMemo(() => new Set(selected ? dependentsOf(edges, selected) : []), [edges, selected]);
  const pick = (name: string) => setSelected((now) => (now === name ? null : name));
  return (
    <div className="tree-analyzer dep-grouped">
      <Impact edges={edges} selected={selected} clear={() => setSelected(null)} />
      <div className="dep-groups">
        {groups.map((g) => (
          <Group key={g.name} edges={edges} name={g.name} links={g.links} loopWords={loopWords} selected={selected} dependents={dependents}
            pick={pick} startOpen={groups.length <= 3} />
        ))}
      </div>
    </div>
  );
}
