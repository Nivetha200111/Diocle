// Parity check: the web Markdown renderer must produce exactly the golden text the Python renderer is tested against,
// and must not throw on an empty or partial `behavior`. Run: npm run check:behavior-md   (Node 22+, no dependencies)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { behaviorMarkdown } from "../lib/behavior-markdown.ts";

const dir = fileURLToPath(new URL("../../../services/converter/tests/fixtures/", import.meta.url));
const got = behaviorMarkdown(JSON.parse(readFileSync(`${dir}behavior-forged.json`, "utf8")));
if (got !== readFileSync(`${dir}behavior-spec.golden.md`, "utf8")) {
  console.error("web Markdown differs from the golden file\n" + got);
  process.exit(1);
}
for (const partial of [{}, { claims: [{}] }, { claims: [{ id: "C1", statement: "s", status: "weird", examples: [{}] }], summary: {} }]) {
  behaviorMarkdown(partial as never);
}
console.log("web Markdown matches the golden file; partial behavior objects render");
