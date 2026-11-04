// Pure graph helpers for the dependency tree view: no model, no API, no dependency. An edge [a, b] means a depends on b,
// exactly as the analyzer reports it (a CALLs or COPYs b, or JCL job a runs program b).

export type Edge = readonly [string, string] | string[];

// Everything that depends on `node`, directly or transitively, nearest first and alphabetical within a distance. Walks
// the edges in reverse with a visited set, so cycles and self-loops end. `node` itself is never listed: it is the selection.
export function dependentsOf(edges: readonly Edge[], node: string): string[] {
  const callers = new Map<string, string[]>();
  for (const [from, to] of edges) {
    if (from !== to) callers.set(to, [...(callers.get(to) ?? []), from]);
  }
  const seen = new Set([node]);
  const out: string[] = [];
  let level = [node];
  while (level.length) {
    const next = new Set<string>();
    for (const n of level) for (const c of callers.get(n) ?? []) if (!seen.has(c)) next.add(c);
    const sorted = [...next].sort();
    sorted.forEach((n) => seen.add(n));
    out.push(...sorted);
    level = sorted;
  }
  return out;
}

export type TreeNode = {
  name: string;
  children: TreeNode[];
  selfLoop: boolean;  // the report has an edge from this name to itself
  shownAbove: boolean;  // this name has links, drawn at its first appearance higher up
};

// A forest that shows every edge exactly once. Roots are the names nothing else points to; a name reached again appears as
// a leaf saying so, which keeps the size linear and ends cycles. A cycle with no way in starts from its first name.
export function buildForest(edges: readonly Edge[]): TreeNode[] {
  const out = new Map<string, Set<string>>();
  const pointedTo = new Set<string>();
  const names = new Set<string>();
  const loops = new Set<string>();
  for (const [from, to] of edges) {
    names.add(from);
    names.add(to);
    if (from === to) {
      loops.add(from);
      continue;
    }
    pointedTo.add(to);
    out.set(from, (out.get(from) ?? new Set<string>()).add(to));
  }
  const expanded = new Set<string>();
  const visit = (name: string): TreeNode => {
    const kids = [...(out.get(name) ?? [])].sort();
    if (expanded.has(name)) return { name, children: [], selfLoop: false, shownAbove: kids.length > 0 || loops.has(name) };
    expanded.add(name);
    return { name, children: kids.map(visit), selfLoop: loops.has(name), shownAbove: false };
  };
  const sorted = [...names].sort();
  const forest = sorted.filter((n) => !pointedTo.has(n)).map(visit);
  for (const n of sorted) if (!expanded.has(n)) forest.push(visit(n));
  return forest;
}

// The one sentence under the tree. It says what the report holds, not what would break at run time.
export function impactLine(edges: readonly Edge[], node: string): string {
  const deps = dependentsOf(edges, node);
  const self = edges.some(([a, b]) => a === node && b === a);
  if (!deps.length) return `If ${node} changes: Nothing here depends on it in the analyzer's report${self ? ", apart from its own link to itself" : ""}.`;
  const verb = deps.length === 1 ? "this 1 depends" : `these ${deps.length} depend`;
  return `If ${node} changes, ${verb} on it in the analyzer's report: ${deps.join(", ")}.`;
}
