// Pure logic: no `vscode` import, so it runs headless in node:test. The glue is in extension.ts.

export type Severity = "error" | "warning" | "note";
export interface Diagnostic { file: string; line: number; severity: Severity; message: string }
export type Assurance = "certified" | "certified-against-repaired-cobol" | "compiled-unverified" | "failed" | "skipped";
export interface EditorResult {
  version: "0.1";
  command: "check" | "convert";
  ok: boolean;
  file?: string;
  error?: string;
  diagnostics?: Diagnostic[];
  assurance?: Assurance;
  assuranceReason?: string;
  runDir?: string;
  files?: { java?: string[]; sqlSchema?: string; repairedCobol?: string; diff?: string; behaviorMd?: string };
  repairedLines?: number;
  costUsd?: number | null;
  maxUsd?: number;
  model?: string | null;
  notes?: string[];
}

export const ASSURANCES: Assurance[] = ["certified", "certified-against-repaired-cobol", "compiled-unverified", "failed", "skipped"];
export const HARD_MAX_USD = 1;

// ---- cobc diagnostics (for text that did not come through the converter, and for tests) ----
const DIAG = /^(.+?):(\d+): (error|warning|note): (.*)$/;
export function parseCobcDiagnostics(text: string): Diagnostic[] {
  const out: Diagnostic[] = [];
  for (const raw of text.split(/\r?\n/)) {
    const m = DIAG.exec(raw.trim());
    if (m && Number(m[2]) >= 1) out.push({ file: m[1], line: Number(m[2]), severity: m[3] as Severity, message: m[4].slice(0, 500) });
    if (out.length >= 200) break;
  }
  return out;
}

// ---- command lines (always an argument array; never a shell string) ----
export interface RunOptions { maxUsd: number; convertAnyway: boolean; copybooks: string[] }
export function clampMaxUsd(v: unknown, fallback = 0.25): number {
  const n = typeof v === "number" && isFinite(v) ? v : fallback;
  return Math.min(HARD_MAX_USD, Math.max(0.01, n));
}
export function buildArgs(command: "check" | "convert", file: string, o: RunOptions): string[] {
  const args = ["-m", "diocle_converter", "editor", command, file];
  for (const c of o.copybooks) args.push("--copybooks", c);
  if (command === "convert") {
    args.push("--max-usd", clampMaxUsd(o.maxUsd).toFixed(2));
    if (o.convertAnyway) args.push("--convert-anyway");
  }
  return args;
}

// ---- result validation (the contract's shape; the extension never trusts the child's stdout blindly) ----
const isStr = (v: unknown): v is string => typeof v === "string";
export function parseResult(stdout: string, expected: "check" | "convert"): { ok: true; value: EditorResult } | { ok: false; error: string } {
  let v: any;
  try { v = JSON.parse(stdout.trim().split("\n").filter(Boolean).pop() ?? ""); } catch { return { ok: false, error: "the converter did not print a JSON result" }; }
  const bad = (why: string) => ({ ok: false as const, error: `unexpected converter output: ${why}` });
  if (!v || typeof v !== "object") return bad("not an object");
  if (v.version !== "0.1") return bad("version");
  if (v.command !== expected) return bad("command");
  if (typeof v.ok !== "boolean") return bad("ok");
  if (v.error !== undefined && !isStr(v.error)) return bad("error");
  if (v.diagnostics !== undefined) {
    if (!Array.isArray(v.diagnostics)) return bad("diagnostics");
    for (const d of v.diagnostics) {
      if (!d || !isStr(d.file) || !Number.isInteger(d.line) || d.line < 1 || !["error", "warning", "note"].includes(d.severity) || !isStr(d.message)) return bad("diagnostic");
    }
  }
  if (expected === "check" && !Array.isArray(v.diagnostics)) return bad("diagnostics missing");
  if (expected === "convert" && v.ok) {
    if (!ASSURANCES.includes(v.assurance)) return bad("assurance");
    if (typeof v.maxUsd !== "number") return bad("maxUsd");
  }
  if (v.files !== undefined) {
    const f = v.files;
    if (!f || typeof f !== "object") return bad("files");
    for (const k of ["sqlSchema", "repairedCobol", "diff", "behaviorMd"]) if (f[k] !== undefined && !isStr(f[k])) return bad("files." + k);
    if (f.java !== undefined && !(Array.isArray(f.java) && f.java.every(isStr))) return bad("files.java");
  }
  for (const k of ["assuranceReason", "runDir", "file"]) if (v[k] !== undefined && !isStr(v[k])) return bad(k);
  if (v.costUsd !== undefined && v.costUsd !== null && typeof v.costUsd !== "number") return bad("costUsd");
  if (v.notes !== undefined && !(Array.isArray(v.notes) && v.notes.every(isStr))) return bad("notes");
  return { ok: true, value: v as EditorResult };
}

// ---- badge wording: the honest text for each label, in one place ----
export interface Badge { label: string; tone: "good" | "caution" | "unverified" | "bad" | "neutral"; text: string }
export function badgeFor(r: Pick<EditorResult, "assurance" | "assuranceReason" | "repairedLines">): Badge {
  const reason = r.assuranceReason ? ` Reason: ${r.assuranceReason}` : "";
  switch (r.assurance) {
    case "certified":
      return { label: "CERTIFIED", tone: "good", text: "The generated Java matched the original COBOL byte for byte on the inputs tried. This is not a proof that the two behave the same on every input." };
    case "certified-against-repaired-cobol": {
      const n = r.repairedLines ?? 0;
      return { label: "CERTIFIED AGAINST REPAIRED COBOL", tone: "caution",
        text: `Your original COBOL did not compile. A model patched ${n} line${n === 1 ? "" : "s"} (the diff is shown) and the Java matched the PATCHED COBOL, not your file. A person must confirm the patch is what the author meant. This is not plain certified.` };
    }
    case "compiled-unverified":
      return { label: "COMPILED, NOT VERIFIED", tone: "unverified", text: `The Java compiles, but it was never run against the original COBOL.${reason}` };
    case "skipped":
      return { label: "SKIPPED", tone: "neutral", text: `Nothing was converted.${reason}` };
    default:
      return { label: "FAILED", tone: "bad", text: `No Java was proven to match.${reason}` };
  }
}

// ---- HTML ----
export function escapeHtml(s: unknown): string {
  return String(s ?? "").replace(/[&<>"'`]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;", "`": "&#96;" }[c] as string));
}

export interface ViewData { result: EditorResult; diffText?: string; costLine?: string }
export const OPEN_KEYS = ["java", "diff", "sqlSchema", "behaviorMd", "folder"] as const;
export function renderResultHtml(d: ViewData, nonce: string, cspSource: string): string {
  const r = d.result;
  const b = badgeFor(r);
  const files = r.files ?? {};
  const btn = (key: string, label: string) => `<button data-open="${escapeHtml(key)}">${escapeHtml(label)}</button>`;
  const buttons = [
    files.java?.length ? btn("java", "Open the generated Java") : "",
    files.repairedCobol && files.diff ? btn("diff", "Compare your COBOL with the repaired COBOL") : "",
    files.sqlSchema ? btn("sqlSchema", "Open schema.sql") : "",
    files.behaviorMd ? btn("behaviorMd", "Open the behaviour spec") : "",
    r.runDir ? btn("folder", "Reveal the run folder") : "",
  ].join(" ");
  const cost = r.costUsd === null || r.costUsd === undefined ? "unknown" : `$${r.costUsd.toFixed(4)}`;
  const diff = d.diffText ? `<h2>COBOL repair (original to patched)</h2><pre>${escapeHtml(d.diffText.slice(0, 20000))}</pre>` : "";
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Diocle result</title>
<style nonce="${nonce}">
body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);padding:16px 20px;line-height:1.5}
.badge{display:inline-block;font-size:1.5em;font-weight:700;padding:8px 16px;border-radius:6px;border:2px solid;letter-spacing:.02em}
.good{color:#1a7f37;border-color:#1a7f37}.caution{color:#9a6700;border-color:#9a6700}.unverified{color:#9a6700;border-color:#9a6700}.bad{color:#cf222e;border-color:#cf222e}.neutral{color:var(--vscode-descriptionForeground);border-color:var(--vscode-descriptionForeground)}
pre{background:var(--vscode-textCodeBlock-background);padding:10px;overflow:auto;white-space:pre-wrap;word-break:break-word}
button{margin:4px 6px 4px 0;padding:5px 10px;background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;border-radius:3px;cursor:pointer}
dl{display:grid;grid-template-columns:max-content 1fr;gap:2px 14px}dt{color:var(--vscode-descriptionForeground)}
</style></head><body>
<div class="badge ${escapeHtml(b.tone)}">${escapeHtml(b.label)}</div>
<p>${escapeHtml(b.text)}</p>
${diff}
<p>${buttons}</p>
<dl><dt>Cost</dt><dd>${escapeHtml(cost)} (cap $${escapeHtml((r.maxUsd ?? 0).toFixed(2))}), your own Meta key</dd>
<dt>Model</dt><dd>${escapeHtml(r.model ?? "unknown")}</dd><dt>File</dt><dd>${escapeHtml(r.file ?? "")}</dd></dl>
<p><small>The code was sent to the Meta Model API with your key. Nothing went to Diocle servers.</small></p>
<script nonce="${nonce}">const vscode=acquireVsCodeApi();document.querySelectorAll("button[data-open]").forEach(b=>b.addEventListener("click",()=>vscode.postMessage({open:b.dataset.open})));</script>
</body></html>`;
}

export function costConfirmText(maxUsd: number, convertAnyway: boolean): string {
  return `Convert and verify this file? It can spend up to $${maxUsd.toFixed(2)} of your own Meta key. The code is sent to the Meta model API; nothing goes to Diocle servers.` +
    (convertAnyway ? " Convert-anyway is on: a file that does not compile may be repaired by the model; that result is labelled and is never plain certified." : "");
}

export function describeResultForStatus(r: EditorResult): string {
  if (r.command === "check") {
    const n = (r.diagnostics ?? []).filter((d) => d.severity === "error").length;
    return r.ok ? "compiles under GnuCOBOL (-std=ibm)" : `${n} compile error${n === 1 ? "" : "s"}`;
  }
  return badgeFor(r).label;
}
