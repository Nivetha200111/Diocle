// Builds lib/dependency-trees.json from the recorded dependency-tree runs in eval/. Re-run it when a results file changes:
//   node apps/web/scripts/build-trees.mjs
// It only reads eval/ and public/trees/, and it stops on anything that would make the page say more than the record does.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const inputs = ["results-dependency-trees.json", "results-dependency-trees-parts.json"].map((f) => join(web, "..", "..", "eval", f));

// Lines the record does not carry, with where each comes from. docs/BLIND_TEST.md: production role not established; a demo.
const NOTES = {
  "navikt-dsf": "Whether these programs ran in production is not established.",
  "core-banking": "A public demo repository.",
};

// A parts file names what it drew in the title, not in "kinds".
function kindsOf(tree) {
  if (tree.slug === "navikt-dsf") return ["call"]; // all 3 edges are CALLs at the pinned commit
  if (tree.kinds?.length) return tree.kinds;
  if (/JCL job/.test(tree.title)) return ["job", "copy"];
  if (/CALLs/.test(tree.title)) return ["call"];
  throw new Error(`${tree.slug}: cannot tell what its edges are`);
}

const trees = [];
for (const file of inputs) {
  if (!existsSync(file)) {
    console.log(`not there yet, skipped: ${file}`);
    continue;
  }
  const isParts = file.endsWith("-parts.json");
  for (const t of JSON.parse(readFileSync(file, "utf8")).trees) {
    if (trees.some((x) => x.slug === t.slug)) throw new Error(`${t.slug}: appears twice`);
    const last = t.attempts.at(-1);
    if (t.verified !== Boolean(last?.match)) throw new Error(`${t.slug}: verified says ${t.verified}, its last attempt says ${last?.match}`);
    if (t.verified && t.image !== last.image) throw new Error(`${t.slug}: the verified image is not the attempt that matched`);
    for (const a of t.attempts) {
      if (!existsSync(join(web, "public", "trees", a.image))) throw new Error(`${t.slug}: public/trees/${a.image} is missing`);
    }
    trees.push({
      slug: t.slug,
      title: t.title,
      part: isParts,
      repository: t.repository,
      commit: t.commit,
      kinds: kindsOf(t),
      note: NOTES[t.slug] ?? null,
      edges: t.edges,
      verified: t.verified,
      image: t.verified ? t.image : null,
      attempts: t.attempts.map((a) => ({
        attempt: a.attempt,
        image: a.image,
        match: a.match,
        missingEdges: a.missingEdges.length,
        inventedEdges: a.inventedEdges.length,
        missingNodes: a.missingNodes.length,
        inventedNodes: a.inventedNodes.length,
      })),
    });
  }
}

// A part must be a piece of its repository's whole tree. A "JOB X" box is the job the whole tree writes as X.
for (const part of trees.filter((t) => t.part)) {
  const whole = trees.find((t) => !t.part && t.repository === part.repository);
  if (!whole) throw new Error(`${part.slug}: no whole-repository tree for ${part.repository}`);
  const known = new Set(whole.edges.map(([a, b]) => `${a} ${b}`));
  for (const [a, b] of part.edges) {
    if (!known.has(`${a.replace(/^JOB /, "")} ${b}`)) throw new Error(`${part.slug}: ${a} -> ${b} is not in ${whole.slug}`);
  }
}

writeFileSync(join(web, "lib", "dependency-trees.json"), JSON.stringify({ source: "Built by scripts/build-trees.mjs from eval/results-dependency-trees*.json", trees }, null, 1) + "\n");
console.log(`${trees.length} trees, ${trees.filter((t) => t.verified).length} with a verified drawing`);
