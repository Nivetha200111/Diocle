// The Smallest reproducer card renders only what reproducerView() returns. Feed it the real example, then odd values: it must never
// throw, every string must be capped, nothing may show "[object Object]", and the opinion label must always read "explanation, not proof".
// Run: npm run check:reproducer-view   (Node 22+, no dependencies)
import { readFileSync } from "node:fs";
import { reproducerView, cap } from "../lib/reproducer-view.ts";

const example = JSON.parse(readFileSync(new URL("../../../contracts/examples/minimal-reproducer.chqclr-nsf-fee.json", import.meta.url), "utf8"));
const v = reproducerView(example);
if (!v) throw new Error("the contract example must render");
if (v.headline !== "1 record → 1 record (40 → 40 bytes)") throw new Error("headline: " + v.headline);
if (!v.needed.some((f) => f.name === "RT-FEE" && f.value === " 1000" && f.view === "CQ-BODY")) throw new Error("RT-FEE should be a needed field");
if (v.neutral.some((f) => f.name === "RT-FEE")) throw new Error("needed field listed as neutral");
if (v.explanation?.label !== "explanation, not proof") throw new Error("label");
if (!v.firstDifference.includes("field CL-FEE")) throw new Error("first difference: " + v.firstDifference);

if (!v.mode.startsWith("strict") || !v.origin.startsWith("REBUILT DEFECT")) throw new Error("mode/origin");

const long = "x".repeat(5000);
const cyc: Record<string, unknown> = {}; cyc.self = cyc;
const odd = [null, undefined, 7, true, long, { a: 1 }, ["z"], cyc, () => 1, "", NaN];
const inputs: unknown[] = [null, undefined, 3, "s", [], {}, { id: "a" }, { id: "a", status: "minimized" }];
for (const o of odd) {
  inputs.push({ id: o, status: o });
  inputs.push({ ...example, id: "a", reduction: o, inputs: o, output: o, explanation: o, regression: o, discrepancy: o });
  inputs.push({ ...example, id: "a", inputs: [{ records: [o, { fields: [o, { name: o, offset: o, length: o, value: o, role: o, view: o }], text: o }] }], output: { original: { records: o }, translated: o, firstDifference: o } });
  inputs.push({ ...example, explanation: { text: o, label: o, source: o }, regression: { dir: o, files: o, replay: o, afterRepair: o } });
}
let shown = 0;
const check = (s: string, max = 201) => {
  if (s.length > max) throw new Error(`too long: ${s.length}`);
  if (s.includes("[object Object]")) throw new Error("[object Object] shown");
  shown++;
};
for (const i of inputs) {
  const x = reproducerView(i);
  if (!x) continue;
  [x.id, x.status, x.reason, x.program, x.source, x.mode, x.origin, x.headline, x.stats, x.stopped, x.discrepancy, x.firstDifference, ...x.inputText, ...x.original, ...x.translated].forEach((s) => check(s, 320));
  [...x.needed, ...x.neutral].forEach((f) => [f.name, f.view, f.where, f.value].forEach((s) => check(s)));
  if (x.explanation) { check(x.explanation.text, 601); if (x.explanation.label !== "explanation, not proof") throw new Error("label"); }
  if (x.regression) [x.regression.dir, x.regression.replay, x.regression.afterRepair, ...x.regression.files].forEach((s) => check(s, 250));
}
if (cap(long, 10).length !== 11) throw new Error("cap");
console.log(`ok: ${inputs.length} inputs, ${shown} strings checked`);
