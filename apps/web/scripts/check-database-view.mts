// The Database comparison panel renders only what databaseView() returns. Feed it numbers, objects, very long strings, null,
// arrays and cyclic objects: it must never throw, every string must be at most 201 characters, and nothing may show "[object Object]".
// Run: npm run check:database-view   (Node 22+, no dependencies)
import { databaseView, cap } from "../lib/database-view.ts";

const long = "x".repeat(5000);
const cyc: Record<string, unknown> = {}; cyc.self = cyc;
const odd = [null, undefined, 7, true, long, { a: 1 }, ["z"], cyc, () => 1, "", NaN];
const inputs: unknown[] = [null, undefined, 3, "s", [], {}, { tables: [] }, { tables: "x" }];
for (const v of odd) {
  inputs.push({ engine: v, engineVersion: v, subset: v, seededFrom: v, tables: [{ name: v, rowsSeeded: v, rowsOriginal: v, rowsConverted: v, match: v, changedFromSeed: v, firstMismatch: { row: v, column: v, original: v, converted: v } }, v] });
  inputs.push({ tables: [{ firstMismatch: v, changedFromSeed: { original: v, converted: v } }] });
}
let shown = 0;
const check = (s: string, max = 201) => {
  if (s.length > max) throw new Error(`too long: ${s.length}`);
  if (s.includes("[object Object]")) throw new Error("[object Object] shown");
  shown++;
};
for (const d of inputs) {
  const v = databaseView(d);
  if (!v) continue;
  check(v.engine, 403); // engine name + version, each capped
  [v.subset, v.seededFrom].forEach((x) => check(x));
  for (const r of v.rows) {
    [r.name, r.seeded, r.after, r.changed, r.status].forEach((x) => check(x));
    if (r.mismatch) Object.values(r.mismatch).forEach((x) => check(x));
    if (r.match && r.status !== "MATCH") throw new Error("match/status disagree");
  }
}
// an object name must be readable JSON, not [object Object]; a cyclic one must say invalid
if (cap({ a: 1 }) !== '{"a":1}') throw new Error("object not shown as JSON");
if (cap(cyc) !== "invalid") throw new Error("cyclic object not 'invalid'");
// only match === true shows MATCH
const v = databaseView({ tables: [{ name: "T", match: "true" }, { name: "U", match: true }, { name: "V", match: false }] });
if (!v || v.rows.map((r) => r.status).join() !== "NOT COMPARED,MATCH,DIFFERS" || !v.bad) throw new Error("status logic");
console.log(`database view: ${inputs.length} odd inputs rendered without throwing (${shown} strings checked)`);
