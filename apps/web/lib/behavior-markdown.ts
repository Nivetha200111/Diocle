// The behaviour spec as Markdown. Mirrors services/converter/diocle_converter/documenter.py to_markdown: every dynamic
// value (model-written or program-written) is flattened to one line and escaped or put in backticks, so it cannot open a
// heading, a tag, a link or a forged verdict line. Both renderers are tested against
// services/converter/tests/fixtures/behavior-spec.golden.md. Tolerant of a partial `behavior` object.
import type { Behavior, ClaimExample, ClaimStatus, FieldValues } from "./runs";

const LABEL: Record<ClaimStatus, string> = { confirmed: "CONFIRMED", refuted: "REFUTED", unchecked: "UNCHECKED" };
const SPECIAL = "\\`*_[]<>#|&!";

export const flat = (t: unknown, limit = 200): string =>
  // eslint-disable-next-line no-control-regex
  String(t ?? "").replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").split(/\s+/).filter(Boolean).join(" ").slice(0, limit);
export const esc = (t: unknown): string => Array.from(flat(t, 400)).map((c) => (SPECIAL.includes(c) ? `\\${c}` : c)).join("");
export const code = (t: unknown): string => "`" + flat(t, 400).replace(/`/g, "'") + "`";
export const fields = (v: FieldValues | null | undefined): string => Object.entries(v ?? {}).map(([k, x]) => `${k}=${x}`).join("  ");

export function expectedLines(e: ClaimExample["expected"] | null | undefined): string[] {
  const x = e ?? {};
  const lines = (x.records ?? []).map((r, i) => `record ${i + 1}: ${fields(r)}`);
  if (x.outputRecordCount !== undefined && x.outputRecordCount !== null) lines.push(`${x.outputRecordCount} output record(s)`);
  if (x.stdoutContains) lines.push(`stdout contains "${x.stdoutContains}"`);
  if (x.returnCode !== undefined && x.returnCode !== null) lines.push(`return code ${x.returnCode}`);
  return lines;
}

export function actualLines(a: NonNullable<ClaimExample["actual"]>, shown: number): string[] {
  const lines = (a.records ?? []).slice(0, Math.max(shown, 1)).map((r, i) => `record ${i + 1}: ${fields(r)}`);
  if (a.outputRecordCount !== undefined && a.outputRecordCount !== null) lines.push(`${a.outputRecordCount} output record(s)`);
  if (a.returnCode !== undefined && a.returnCode !== null) lines.push(`return code ${a.returnCode}`);
  return lines;
}

export function behaviorMarkdown(b: Partial<Behavior>): string {
  const s = { claims: 0, confirmed: 0, refuted: 0, unchecked: 0, examplesRun: 0, ...(b.summary ?? {}) };
  const out = [
    `# Behaviour spec: ${esc(b.program)}`,
    "",
    `${s.confirmed} of ${s.claims} claims confirmed on the examples tried (${s.refuted} refuted, ${s.unchecked} unchecked).`,
    "",
    `Written by ${code(b.model)}; every example was run on the original COBOL (${code(b.checkedWith)}). GnuCOBOL decided, not the model. ` +
      `The examples' stated expectations held on GnuCOBOL; the sentence of a claim is not itself machine-checked. ` +
      `"Confirmed" means the examples tried matched, not that the claim is proven.`,
    "",
  ];
  if (b.skipped) return [...out, `Not written: ${esc(b.skipped)}`, ""].join("\n");
  for (const c of b.claims ?? []) {
    out.push(`## ${esc(c.id)} [${LABEL[c.status] ?? "UNCHECKED"}] ${esc(c.statement)}`, "");
    if (c.reason) out.push(`Unchecked: ${esc(c.reason)}`, "");
    for (const e of c.examples ?? []) {
      out.push(`- ${esc(e.id)} [${String(e.status ?? "unchecked").toUpperCase()}]`);
      out.push(`  - input: ${code((e.inputs ?? []).map(fields).join(" | "))}`);
      out.push(`  - expected: ${code(expectedLines(e.expected).join("; "))}`);
      if (e.actual) out.push(`  - actual (GnuCOBOL): ${code(actualLines(e.actual, (e.expected?.records ?? []).length).join("; "))}`);
      for (const m of e.mismatches ?? []) out.push(`  - differed at ${code(m.what)}: expected ${code(m.expected)}, GnuCOBOL produced ${code(m.actual)}`);
      if (e.reason) out.push(`  - unchecked: ${esc(e.reason)}`);
    }
    out.push("");
  }
  return out.join("\n");
}
