// Checks the impact walk and the tree on known cases and on every recorded tree. Run: npm run check:dependency-impact
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { buildForest, dependentsOf, impactLine, type TreeNode } from "../lib/dependency-impact.ts";

const data = JSON.parse(readFileSync(new URL("../lib/dependency-trees.json", import.meta.url), "utf8"));
const edgesOf = (slug: string) => data.trees.find((t: { slug: string }) => t.slug === slug).edges;

// fzn0x core-banking: BANK-MAIN depends on TRANS-PROC, which depends on SYSTEM.
const bank = edgesOf("core-banking");
assert.deepEqual(dependentsOf(bank, "SYSTEM"), ["TRANS-PROC", "BANK-MAIN"]);
assert.equal(impactLine(bank, "SYSTEM"), "If SYSTEM changes, these 2 depend on it in the analyzer's report: TRANS-PROC, BANK-MAIN.");
assert.deepEqual(dependentsOf(bank, "BANK-MAIN"), []);
assert.match(impactLine(bank, "BANK-MAIN"), /Nothing here depends on it/);
assert.equal(impactLine(bank, "TRANS-PROC"), "If TRANS-PROC changes, this 1 depends on it in the analyzer's report: BANK-MAIN.");

// A JCL job and a program with one name: an edge to itself is not a dependent, and it ends.
const quill = edgesOf("quillmark-legacy");
assert.deepEqual(dependentsOf(quill, "ACCTMTCH"), []);
assert.match(impactLine(quill, "ACCTMTCH"), /Nothing here depends on it .*apart from its own link to itself/);
assert.deepEqual(dependentsOf(quill, "MSTREC"), ["ACCTMTCH"]);
assert.deepEqual(dependentsOf(edgesOf("quillmark-acctmtch"), "MSTREC"), ["ACCTMTCH", "JOB ACCTMTCH"]);

// Cycles end, and a cycle with no way in is still drawn.
const cycle = [["A", "B"], ["B", "C"], ["C", "A"], ["X", "A"], ["D", "D"]];
assert.deepEqual(dependentsOf(cycle, "A"), ["C", "X", "B"]);
assert.deepEqual(dependentsOf(cycle, "D"), []);
assert.deepEqual(dependentsOf(cycle, "NOT-THERE"), []);
const closed = [["P", "Q"], ["Q", "P"]];
assert.deepEqual(buildForest(closed).map((n) => n.name), ["P"]);
assert.deepEqual(dependentsOf(closed, "P"), ["Q"]);

// Every recorded tree: the forest draws exactly the report's edges, each once, and every name appears.
function walk(n: TreeNode, out: string[], seen: Set<string>) {
  seen.add(n.name);
  if (n.selfLoop) out.push(`${n.name} ${n.name}`);
  for (const c of n.children) {
    out.push(`${n.name} ${c.name}`);
    walk(c, out, seen);
  }
}
for (const edges of [...data.trees.map((t: { edges: string[][] }) => t.edges), cycle, closed]) {
  const drawn: string[] = [];
  const seen = new Set<string>();
  for (const root of buildForest(edges)) walk(root, drawn, seen);
  assert.deepEqual([...drawn].sort(), edges.map(([a, b]: string[]) => `${a} ${b}`).sort());
  assert.deepEqual([...seen].sort(), [...new Set(edges.flat() as string[])].sort());
}

console.log(`dependency impact: ok, on ${data.trees.length} recorded trees and the known cases`);
