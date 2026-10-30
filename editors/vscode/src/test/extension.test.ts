// Headless check of the extension entry point against a stub of the `vscode` module.
import test from "node:test";
import assert from "node:assert/strict";
import Module from "node:module";
import * as fs from "node:fs";
import * as path from "node:path";

test("activate registers exactly the commands package.json declares", () => {
  const registered: string[] = [];
  const stub: any = new Proxy({
    languages: { createDiagnosticCollection: () => ({ dispose() {}, clear() {}, set() {} }) },
    window: { createOutputChannel: () => ({ dispose() {}, appendLine() {}, show() {} }) },
    commands: { registerCommand: (id: string) => { registered.push(id); return { dispose() {} }; } },
  }, { get: (t: any, k: string) => (k in t ? t[k] : {}) });
  const orig = (Module as any)._load;
  (Module as any)._load = function (req: string, ...rest: unknown[]) { return req === "vscode" ? stub : orig.call(this, req, ...rest); };
  try {
    const ext = require("../extension");
    ext.activate({ subscriptions: [], workspaceState: { get() {}, update() {} } });
  } finally { (Module as any)._load = orig; }
  const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "..", "package.json"), "utf8"));
  assert.deepEqual(registered.sort(), pkg.contributes.commands.map((c: any) => c.command).sort());
  assert.equal(pkg.capabilities.untrustedWorkspaces.supported, false);
  assert.ok(!pkg.contributes.commands.some((c: any) => /language/i.test(c.command)) && !pkg.contributes.languages, "no language of our own");
  assert.ok(!Object.keys(pkg.contributes.configuration.properties).some((k) => /key|token|secret/i.test(k)), "no key setting");
});
