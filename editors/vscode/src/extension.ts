import * as vscode from "vscode";
import { spawn, ChildProcess } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { randomBytes } from "node:crypto";
import * as core from "./core";

const CHECK_TIMEOUT_MS = 90_000;
const CONVERT_TIMEOUT_MS = 35 * 60_000;
const MAX_STDOUT = 5_000_000;
const LAST_KEY = "diocle.lastResult";

let diagnostics: vscode.DiagnosticCollection;
let output: vscode.OutputChannel;
let panel: vscode.WebviewPanel | undefined;

export function activate(context: vscode.ExtensionContext): void {
  diagnostics = vscode.languages.createDiagnosticCollection("diocle");
  output = vscode.window.createOutputChannel("Diocle");
  context.subscriptions.push(diagnostics, output,
    vscode.commands.registerCommand("diocle.check", (uri?: vscode.Uri) => check(uri)),
    vscode.commands.registerCommand("diocle.convert", (uri?: vscode.Uri) => convert(context, uri)),
    vscode.commands.registerCommand("diocle.openLast", () => openLast(context)),
    vscode.commands.registerCommand("diocle.settings", () => showSettings(context)));
}
export function deactivate(): void { panel?.dispose(); }

// ---- helpers ----
function cfg() { return vscode.workspace.getConfiguration("diocle"); }

async function target(uri?: vscode.Uri): Promise<{ file: string; folder: string } | undefined> {
  const u = uri ?? vscode.window.activeTextEditor?.document.uri;
  if (!u || u.scheme !== "file") { vscode.window.showWarningMessage("Diocle: open a saved COBOL file first."); return undefined; }
  const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === u.toString());
  if (doc?.isDirty) await doc.save();  // the converter reads the file on disk; the file is never rewritten by Diocle
  const folder = vscode.workspace.getWorkspaceFolder(u)?.uri.fsPath ?? path.dirname(u.fsPath);
  return { file: u.fsPath, folder };
}

function pythonFor(folder: string): string {
  const set = cfg().get<string>("converterPython", "").trim();
  if (set) return set;
  for (const rel of ["services/converter/.venv/bin/python", "services/converter/.venv/Scripts/python.exe"]) {
    const p = path.join(folder, rel);
    if (fs.existsSync(p)) return p;
  }
  return "python3";
}

function copybookDirs(folder: string): string[] {
  return cfg().get<string[]>("copybookPaths", []).filter((s) => typeof s === "string" && s.trim()).map((s) => path.resolve(folder, s));
}

function killTree(child: ChildProcess): void {
  if (!child.pid) return;
  try {
    if (process.platform === "win32") spawn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
    else process.kill(-child.pid, "SIGKILL");  // the child leads its own process group
  } catch { try { child.kill("SIGKILL"); } catch { /* already gone */ } }
}

interface Spawned { stdout: string; code: number | null; timedOut: boolean; cancelled: boolean; stderrTail: string }
function runConverter(python: string, args: string[], cwd: string, timeoutMs: number, onProgress: (t: string) => void,
                      token?: vscode.CancellationToken): Promise<Spawned> {
  return new Promise((resolve) => {
    // Argument array, no shell: file names are never interpolated into a command string.
    const child = spawn(python, args, { cwd, shell: false, detached: process.platform !== "win32", env: { ...process.env, PYTHONSAFEPATH: "1" }, windowsHide: true });
    let stdout = "", errBuf = "", tail = "", timedOut = false, cancelled = false;
    const timer = setTimeout(() => { timedOut = true; killTree(child); }, timeoutMs);
    token?.onCancellationRequested(() => { cancelled = true; killTree(child); });
    child.stdout!.on("data", (d) => { if (stdout.length < MAX_STDOUT) stdout += d.toString("utf8"); });
    child.stderr!.on("data", (d) => {
      errBuf += d.toString("utf8");
      let i: number;
      while ((i = errBuf.indexOf("\n")) >= 0) {
        const line = errBuf.slice(0, i).replace(/\r$/, ""); errBuf = errBuf.slice(i + 1);
        output.appendLine(line);
        if (line.startsWith("PROGRESS ")) onProgress(line.slice(9)); else tail = (tail + "\n" + line).slice(-600);
      }
    });
    child.on("error", (e) => { clearTimeout(timer); resolve({ stdout, code: null, timedOut, cancelled, stderrTail: `could not start ${python}: ${e.message}` }); });
    child.on("close", (code) => { clearTimeout(timer); resolve({ stdout, code, timedOut, cancelled, stderrTail: tail.trim() }); });
  });
}

// ---- check ----
async function check(uri?: vscode.Uri): Promise<void> {
  const t = await target(uri);
  if (!t) return;
  diagnostics.clear();
  const args = core.buildArgs("check", t.file, { maxUsd: 0.25, convertAnyway: false, copybooks: copybookDirs(t.folder) });
  const res = await vscode.window.withProgress({ location: vscode.ProgressLocation.Notification, title: "Diocle: compiling with GnuCOBOL" },
    () => runConverter(pythonFor(t.folder), args, t.folder, CHECK_TIMEOUT_MS, () => undefined));
  const parsed = core.parseResult(res.stdout, "check");
  if (!parsed.ok) return fail(res.timedOut ? "compiling timed out" : parsed.error, res.stderrTail);
  const r = parsed.value;
  if (r.error) return fail(r.error, "");
  const byFile = new Map<string, vscode.Diagnostic[]>();
  for (const d of r.diagnostics ?? []) {
    const abs = path.isAbsolute(d.file) ? d.file : fs.existsSync(path.resolve(t.folder, d.file)) ? path.resolve(t.folder, d.file) : t.file;
    const line = d.line - 1;
    const sev = d.severity === "error" ? vscode.DiagnosticSeverity.Error : d.severity === "warning" ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Information;
    const diag = new vscode.Diagnostic(new vscode.Range(line, 0, line, 1000), d.message, sev);
    diag.source = "GnuCOBOL (cobc -std=ibm)";
    byFile.set(abs, [...(byFile.get(abs) ?? []), diag]);
  }
  for (const [f, list] of byFile) diagnostics.set(vscode.Uri.file(f), list);
  if (r.ok) vscode.window.showInformationMessage(`Diocle: ${path.basename(t.file)} ${core.describeResultForStatus(r)}.`);
  else vscode.window.showWarningMessage(`Diocle: ${path.basename(t.file)}: ${core.describeResultForStatus(r)}. See the Problems panel.`);
}

function fail(message: string, detail: string): void {
  output.appendLine(`ERROR ${message}`);
  vscode.window.showErrorMessage(`Diocle: ${message}${detail ? ` (${detail.split("\n").pop()})` : ""}`, "Show log").then((c) => { if (c) output.show(); });
}

// ---- convert ----
async function convert(context: vscode.ExtensionContext, uri?: vscode.Uri): Promise<void> {
  const t = await target(uri);
  if (!t) return;
  const maxUsd = core.clampMaxUsd(cfg().get<number>("maxUsd", 0.25));
  const anyway = cfg().get<boolean>("convertAnyway", false);
  if (cfg().get<boolean>("confirmCost", true)) {
    const go = "Convert";
    const never = "Convert, don't ask again";
    const pick = await vscode.window.showWarningMessage(core.costConfirmText(maxUsd, anyway), { modal: true }, go, never);
    if (!pick) return;
    if (pick === never) await cfg().update("confirmCost", false, vscode.ConfigurationTarget.Global);
  }
  const args = core.buildArgs("convert", t.file, { maxUsd, convertAnyway: anyway, copybooks: copybookDirs(t.folder) });
  const res = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Diocle: converting ${path.basename(t.file)}`, cancellable: true },
    (progress, token) => runConverter(pythonFor(t.folder), [...args, "--runs-dir", path.join(t.folder, ".diocle", "runs")], t.folder, CONVERT_TIMEOUT_MS,
      (text) => progress.report({ message: text.slice(0, 120) }), token));
  if (res.cancelled) return void vscode.window.showInformationMessage("Diocle: conversion cancelled. Model calls already made may have been billed.");
  const parsed = core.parseResult(res.stdout, "convert");
  if (!parsed.ok) return fail(res.timedOut ? "the conversion timed out" : parsed.error, res.stderrTail);
  if (!parsed.value.ok) return fail(parsed.value.error ?? "the conversion could not run", res.stderrTail);
  await context.workspaceState.update(LAST_KEY, parsed.value);
  await showResult(context, parsed.value);
}

async function openLast(context: vscode.ExtensionContext): Promise<void> {
  const last = context.workspaceState.get<core.EditorResult>(LAST_KEY);
  const check = last && core.parseResult(JSON.stringify(last), "convert");
  if (!check || !check.ok) return void vscode.window.showInformationMessage("Diocle: no result yet. Run a conversion first.");
  await showResult(context, check.value);
}

/** Only paths the converter reported for THIS result can be opened, and only by key: the webview sends a key, never a path. */
function openables(r: core.EditorResult): Record<string, string | undefined> {
  const f = r.files ?? {};
  return { java: f.java?.[0], sqlSchema: f.sqlSchema, behaviorMd: f.behaviorMd, folder: r.runDir, diff: f.repairedCobol };
}

async function showResult(context: vscode.ExtensionContext, r: core.EditorResult): Promise<void> {
  let diffText: string | undefined;
  if (r.files?.diff) { try { diffText = fs.readFileSync(r.files.diff, "utf8"); } catch { /* shown without it */ } }
  panel?.dispose();
  panel = vscode.window.createWebviewPanel("diocleResult", `Diocle: ${r.assurance ? core.badgeFor(r).label : "result"}`, vscode.ViewColumn.Beside,
    { enableScripts: true, localResourceRoots: [], retainContextWhenHidden: false });
  const nonce = randomBytes(16).toString("hex");
  panel.webview.html = core.renderResultHtml({ result: r, diffText }, nonce, panel.webview.cspSource);
  panel.webview.onDidReceiveMessage(async (m: { open?: string }) => {
    const key = m?.open;
    if (typeof key !== "string" || !(core.OPEN_KEYS as readonly string[]).includes(key)) return;
    const p = openables(r)[key];
    if (!p) return;
    // the paths come from the converter's JSON: open only what lies inside the run folder (the repaired-COBOL diff's original is the user's own file)
    if (r.runDir && !path.resolve(p).startsWith(path.resolve(r.runDir) + path.sep) && path.resolve(p) !== path.resolve(r.runDir)) return;
    if (key === "folder") return void vscode.commands.executeCommand("revealFileInOS", vscode.Uri.file(p));
    if (key === "diff") {
      const original = r.file ? vscode.Uri.file(r.file) : undefined;
      if (original) return void vscode.commands.executeCommand("vscode.diff", original, vscode.Uri.file(p), "Your COBOL <-> repaired COBOL (a person must confirm)");
    }
    await vscode.window.showTextDocument(vscode.Uri.file(p), { viewColumn: vscode.ViewColumn.One, preview: false });
  }, undefined, context.subscriptions);
  if (r.files?.java?.[0]) await vscode.window.showTextDocument(vscode.Uri.file(r.files.java[0]), { viewColumn: vscode.ViewColumn.One, preview: false, preserveFocus: true });
}

// ---- cost and settings ----
async function showSettings(context: vscode.ExtensionContext): Promise<void> {
  const last = context.workspaceState.get<core.EditorResult>(LAST_KEY);
  const cap = core.clampMaxUsd(cfg().get<number>("maxUsd", 0.25));
  const lastLine = last ? `Last conversion: ${last.costUsd == null ? "cost unknown" : "$" + last.costUsd.toFixed(4)} (${last.model ?? "model unknown"}).` : "No conversion yet.";
  const pick = await vscode.window.showInformationMessage(
    `Diocle: cap $${cap.toFixed(2)} per conversion, convert-anyway ${cfg().get("convertAnyway") ? "on" : "off"}. ${lastLine} The Meta key is read by the converter from your environment or the workspace .env; it is not an editor setting.`,
    "Open settings");
  if (pick) await vscode.commands.executeCommand("workbench.action.openSettings", "diocle");
}
