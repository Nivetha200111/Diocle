import test from "node:test";
import assert from "node:assert/strict";
import * as core from "../core";

test("cobc diagnostics: only file:line: severity: text lines", () => {
  const d = core.parseCobcDiagnostics("/w/a.cbl:12: error: 'X' is not defined\n   12 |  MOVE X\n/w/c.cpy:3: warning: odd\nnoise");
  assert.deepEqual(d, [
    { file: "/w/a.cbl", line: 12, severity: "error", message: "'X' is not defined" },
    { file: "/w/c.cpy", line: 3, severity: "warning", message: "odd" }]);
});

test("command lines are argument arrays with the cap clamped", () => {
  const a = core.buildArgs("convert", "/w/my file; rm -rf.cbl", { maxUsd: 99, convertAnyway: true, copybooks: ["/c1", "c 2"] });
  assert.deepEqual(a, ["-m", "diocle_converter", "editor", "convert", "/w/my file; rm -rf.cbl", "--copybooks", "/c1", "--copybooks", "c 2", "--max-usd", "1.00", "--convert-anyway"]);
  assert.deepEqual(core.buildArgs("check", "a.cbl", { maxUsd: 0.25, convertAnyway: true, copybooks: [] }), ["-m", "diocle_converter", "editor", "check", "a.cbl"]);
  assert.equal(core.clampMaxUsd(NaN), 0.25);
  assert.equal(core.clampMaxUsd(0), 0.01);
});

test("result parsing accepts the contract shape and rejects the rest", () => {
  const good = JSON.stringify({ version: "0.1", command: "check", ok: false, diagnostics: [{ file: "a", line: 5, severity: "error", message: "m" }] });
  assert.equal(core.parseResult("noise\n" + good + "\n", "check").ok, true);
  for (const bad of ['{"version":"0.2","command":"check","ok":true,"diagnostics":[]}',
    '{"version":"0.1","command":"convert","ok":true,"diagnostics":[]}',
    '{"version":"0.1","command":"check","ok":true}',
    '{"version":"0.1","command":"check","ok":true,"diagnostics":[{"file":"a","line":0,"severity":"error","message":"m"}]}',
    '{"version":"0.1","command":"convert","ok":true,"assurance":"proven","maxUsd":1}',
    '{"version":"0.1","command":"convert","ok":true,"assurance":"certified"}',
    '{"version":"0.1","command":"convert","ok":true,"assurance":"certified","maxUsd":1,"files":{"java":"x"}}',
    "not json", ""]) {
    assert.equal(core.parseResult(bad, bad.includes('"convert"') && !bad.includes('"command":"check"') ? "convert" : "check").ok, false, bad);
  }
  assert.equal(core.parseResult('{"version":"0.1","command":"convert","ok":false,"error":"no key"}', "convert").ok, true);
});

test("badge wording: certified only for plain certified", () => {
  assert.equal(core.badgeFor({ assurance: "certified" }).label, "CERTIFIED");
  assert.match(core.badgeFor({ assurance: "certified" }).text, /byte for byte on the inputs tried.*not a proof/);
  const rep = core.badgeFor({ assurance: "certified-against-repaired-cobol", repairedLines: 1 });
  assert.equal(rep.label, "CERTIFIED AGAINST REPAIRED COBOL");
  assert.match(rep.text, /patched 1 line /); assert.match(rep.text, /person must confirm/); assert.match(rep.text, /not plain certified/);
  const un = core.badgeFor({ assurance: "compiled-unverified", assuranceReason: "EXEC SQL" });
  assert.equal(un.label, "COMPILED, NOT VERIFIED"); assert.match(un.text, /never run against the original/); assert.match(un.text, /EXEC SQL/);
  assert.equal(core.badgeFor({ assurance: "failed" }).label, "FAILED");
  assert.equal(core.badgeFor({}).label, "FAILED");
  for (const a of core.ASSURANCES.filter((x) => x !== "certified")) assert.notEqual(core.badgeFor({ assurance: a }).label, "CERTIFIED");
});

test("html escaping and strict CSP; model-written text cannot inject", () => {
  assert.equal(core.escapeHtml(`<img src=x onerror="a()">&'\``), "&lt;img src=x onerror=&quot;a()&quot;&gt;&amp;&#39;&#96;");
  const evil = "<script>alert(1)</script>";
  const html = core.renderResultHtml({
    result: { version: "0.1", command: "convert", ok: true, assurance: "compiled-unverified", assuranceReason: evil, maxUsd: 0.25, costUsd: 0.01, model: evil, file: evil, runDir: "/r", files: { java: ["/r/A.java"] } },
    diffText: "-" + evil + "\n+x" }, "N0NCE", "vscode-resource:");
  assert.ok(!html.includes(evil));
  assert.match(html, /default-src 'none'; style-src 'nonce-N0NCE'; script-src 'nonce-N0NCE'/);
  assert.ok(!/https?:\/\//.test(html), "no remote resources");
  assert.equal((html.match(/<script/g) ?? []).length, 1);
  assert.match(html, /COMPILED, NOT VERIFIED/);
});

test("cost confirmation names the cap, the destination and the label rule", () => {
  const t = core.costConfirmText(0.25, true);
  assert.match(t, /up to \$0\.25 of your own Meta key/); assert.match(t, /nothing goes to Diocle servers/); assert.match(t, /never plain certified/);
});
