"""Tests for the Diocle MCP server (editors/muse-code/plugin/mcp/server.py). Run:
  DIOCLE_PYTHON=services/converter/.venv/bin/python services/converter/.venv/bin/python -m pytest editors/muse-code/tests
The server itself is standard library only. The two tests that run the real analyzer and verifier are skipped unless a Diocle
venv python (DIOCLE_PYTHON, or services/*/.venv in the repo), cobc 3.2 and JDK 21 are available."""
import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent / "plugin" / "mcp" / "server.py"
sys.path.insert(0, str(SERVER.parent))
import server  # noqa: E402

REPO = server.repo_root()
def _py_ok():
    env = server.child_env(REPO)
    r = subprocess.run([server.python_exe(REPO), "-P", "-c", "import diocle_analyzer, diocle_verifier"], env=env, capture_output=True)
    return r.returncode == 0


HAVE_TOOLCHAIN = bool(shutil.which("cobc") and shutil.which("javac") and _py_ok())


def rpc(proc, method, params=None, i=1, notify=False):
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not notify:
        msg["id"] = i
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    if notify:
        return None
    return json.loads(proc.stdout.readline())


@pytest.fixture()
def proc(tmp_path):
    env = {**os.environ, "DIOCLE_MCP_CONFIG_DIR": str(tmp_path / "cfg")}
    env.pop("DIOCLE_MCP_ALLOW_CONVERT", None)
    p = subprocess.Popen([sys.executable, str(SERVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=env)
    yield p
    p.stdin.close()
    p.wait(timeout=5)


def call(name, args):
    r = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})
    return r["result"]["isError"], r["result"]["content"][0]["text"]


def test_handshake_and_lists(proc):
    r = rpc(proc, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
    assert r["result"]["serverInfo"]["name"] == "diocle" and r["result"]["protocolVersion"] == "2025-06-18"
    assert set(r["result"]["capabilities"]) == {"tools", "resources", "prompts"}
    assert rpc(proc, "notifications/initialized", notify=True) is None
    names = {t["name"] for t in rpc(proc, "tools/list", i=2)["result"]["tools"]}
    assert names == {"diocle_analyze", "diocle_verify_stored", "diocle_live_run", "diocle_convert", "diocle_explain",
                     "diocle_coverage", "diocle_mutation_report"}
    assert any(r["uri"].startswith("diocle://samples/interest-accrual/src/") for r in rpc(proc, "resources/list", i=3)["result"]["resources"])
    assert {p["name"] for p in rpc(proc, "prompts/list", i=4)["result"]["prompts"]} == {"certify-a-cobol-program", "explain-a-run"}
    pr = rpc(proc, "prompts/get", {"name": "certify-a-cobol-program", "arguments": {"sample": "interest-accrual"}}, i=5)
    assert "samples/interest-accrual" in pr["result"]["messages"][0]["content"]["text"]
    assert rpc(proc, "ping", i=6)["result"] == {}


def test_protocol_errors(proc):
    assert rpc(proc, "nope", i=1)["error"]["code"] == -32601
    assert rpc(proc, "tools/call", {"name": "rm_rf", "arguments": {}}, i=2)["error"]["code"] == -32602
    proc.stdin.write("{not json\n"); proc.stdin.flush()
    assert json.loads(proc.stdout.readline())["error"]["code"] == -32700
    assert server.handle({"jsonrpc": "2.0", "id": 3, "method": "initialize", "params": {"protocolVersion": "1999"}})["result"]["protocolVersion"] == "2025-06-18"


def test_resources_read_and_validation():
    uri = "diocle://samples/interest-accrual/src/INTACCR.cbl"
    assert "PROGRAM-ID" in server.read_resource(uri)["text"].upper()
    for bad in ("diocle://samples/../README.md", "diocle://samples/interest-accrual/src/../../../README.md",
                "diocle://samples/interest-accrual/src/INTACCR.cbl/x", "file:///etc/passwd", "diocle://samples/interest-accrual/certified-java/IntAccr.java"):
        with pytest.raises(server.ToolError):
            server.read_resource(bad)


@pytest.mark.parametrize("path", ["/etc", "../../../etc", "samples/../../..", "~", "/etc/passwd", "samples/interest-accrual/../../../..", ""])
def test_analyze_path_escape_rejected(path):
    err, text = call("diocle_analyze", {"path": path})
    assert err and ("outside" in text or "non-empty" in text)


def test_analyze_symlink_escape_rejected(tmp_path, monkeypatch):
    root = tmp_path / "repo"; (root / "samples" / "x").mkdir(parents=True)
    (root / "samples" / "x" / "evil.cbl").symlink_to("/etc/hosts")
    monkeypatch.setenv("DIOCLE_REPO", str(root))
    err, text = call("diocle_analyze", {"path": "samples/x"})
    assert err and "outside the repository" in text
    (root / "link").symlink_to("/etc")
    err, text = call("diocle_analyze", {"path": "link"})
    assert err and "outside the Diocle repository" in text


def test_names_and_arguments_validated():
    for bad in ("../x", "a b", "a;b", "x/y", "$(id)", "", "a" * 70, None, 5):
        assert call("diocle_verify_stored", {"sample": bad})[0]
    assert call("diocle_verify_stored", {"sample": "interest-accrual", "random": 5})[0]
    assert call("diocle_verify_stored", {"sample": "interest-accrual", "random": "9"})[0]
    assert call("diocle_verify_stored", {"sample": "no-such-sample"})[0]
    assert call("diocle_live_run", {"run_id": "../../etc/passwd"})[0]
    assert call("diocle_live_run", {"run_id": "A B"})[0]
    assert call("diocle_explain", {"run": "samples/interest-accrual"})[0]
    assert call("diocle_explain", {"run": "/etc"})[0]


def test_convert_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("DIOCLE_MCP_ALLOW_CONVERT", raising=False)
    monkeypatch.setenv("DIOCLE_MCP_CONFIG_DIR", str(tmp_path / "none"))
    err, text = call("diocle_convert", {"sample": "interest-accrual"})
    assert err and "disabled" in text and "Nothing was run" in text


def test_convert_cap_and_no_key_argument(tmp_path, monkeypatch):
    monkeypatch.setenv("DIOCLE_MCP_ALLOW_CONVERT", "1")
    called = []
    monkeypatch.setattr(server, "run_argv", lambda *a, **k: called.append(a) or (1, "boom"))
    for bad in (0.26, 5, 0, -1, "0.1", True):
        assert call("diocle_convert", {"sample": "interest-accrual", "max_usd": bad})[0]
    err, text = call("diocle_convert", {"sample": "interest-accrual", "api_key": "sk-secret-secret-secret"})
    assert err and "sk-secret" not in text and "never an argument" in text
    assert not called  # nothing ran for any rejected call
    err, text = call("diocle_convert", {"sample": "interest-accrual"})  # allowed: default cap is passed to the converter
    argv = called[0][0]
    assert "--max-usd" in argv and argv[argv.index("--max-usd") + 1] == "0.10" and "--no-memory" in argv
    assert isinstance(argv, list)


def test_convert_marker_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DIOCLE_MCP_ALLOW_CONVERT", raising=False)
    monkeypatch.setenv("DIOCLE_MCP_CONFIG_DIR", str(tmp_path))
    assert not server.convert_allowed()
    (tmp_path / "allow-convert").write_text("")
    assert server.convert_allowed()


def test_scrub_and_cap(monkeypatch):
    monkeypatch.setenv("META_MODEL_API_KEY", "supersecretvalue12345")
    out = server.cap("leak supersecretvalue12345 and Bearer abcdefghijklmnop1234 and sk-abcdefghijklmnopqrstuv")
    assert "supersecret" not in out and "abcdefghijklmnop1234" not in out and "sk-abcdef" not in out
    assert "truncated" in server.cap("x" * 40000)
    env = server.child_env(REPO)
    assert "META_MODEL_API_KEY" not in env
    monkeypatch.setenv("MODEL_MODE", "hosted")
    assert "META_MODEL_API_KEY" in server.child_env(REPO, with_model=True)


def make_run(root: Path, name="demo-20261030-000000", certified=True):
    d = root / "runs" / name; d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"program": "DEMO", "command": "run", "status": "certified" if certified else "failed",
        "certified": certified, "rounds": [{"round": 1, "certified": certified, "seed": 4243, "summary": {"total": 1027, "passed": 1027, "failed": 0}}],
        "usage": {"calls": 3, "inputTokens": 10, "outputTokens": 20, "estimatedCostUsd": 0.0123}, "javaOrigin": "translated by a model"}))
    return d


def test_explain_and_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("DIOCLE_REPO", str(tmp_path))
    d = make_run(tmp_path)
    err, text = call("diocle_explain", {"run": f"runs/{d.name}"})
    assert not err and "CERTIFIED" in text and "1027 of 1027" in text and "not a proof" in text and "0.0123" in text
    err, text = call("diocle_mutation_report", {"run": f"runs/{d.name}"})
    assert not err and "No mutation-report.json" in text
    (d / "mutation-report.json").write_text(json.dumps({"program": "DEMO", "counts": {"detected": 3, "survived": 1}, "mutants": [
        {"id": "m1", "operator": "relational-swap", "location": {"file": "A.java", "line": 3}, "description": "x", "outcome": "survived"}]}))
    err, text = call("diocle_mutation_report", {"run": f"runs/{d.name}"})
    assert not err and "relational-swap" in text and "coverage question" in text
    assert call("diocle_explain", {"run": "runs/../README.md"})[0]


def test_coverage():
    err, text = call("diocle_coverage", {})
    assert not err and "refusedOrLimited" in text and "interest-accrual" in text


class _H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"/runs": [{"id": "chqclr-1", "program": "CHQCLR", "certified": True}],
                "/runs/chqclr-1": {"id": "chqclr-1", "program": "CHQCLR", "certified": True, "status": "certified",
                                   "after": {"total": 10, "passed": 10, "failed": 0}, "usage": {"calls": 2, "estimatedCostUsd": 0.01}}}.get(self.path)
        self.send_response(200 if body else 404); self.end_headers()
        self.wfile.write(json.dumps(body or {}).encode())

    def log_message(self, *a): pass


def test_live_run_against_local_stub(monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), _H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_API_BASE", f"http://127.0.0.1:{srv.server_port}")
    try:
        err, text = call("diocle_live_run", {"run_id": "chqclr-1"})
        assert not err and '"certified":true' in text and "not proven equivalent" in text
        assert not call("diocle_live_run", {})[0]
        err, text = call("diocle_live_run", {"run_id": "missing-run"})
        assert err and "404" in text
    finally:
        srv.shutdown()
    monkeypatch.setenv("DIOCLE_API_BASE", "http://evil.example")
    assert call("diocle_live_run", {"run_id": "chqclr-1"})[0]


@pytest.mark.skipif(not HAVE_TOOLCHAIN, reason="needs a Diocle venv python (DIOCLE_PYTHON), cobc 3.2 and JDK 21")
def test_analyze_real_sample():
    err, text = call("diocle_analyze", {"path": "samples/interest-accrual"})
    data = json.loads(text)
    assert not err and data["programs"][0]["program"] == "INTACCR" and data["programs"][0]["convertible"] is True
    assert any(f["category"] == "rounding" for f in data["riskFindings"])
    err, text = call("diocle_analyze", {"path": "samples/db2-dynamic-sql"})
    assert "outside the verified subset" in text
    err, text = call("diocle_analyze", {"path": "samples/interest-accrual/src/INTACCR.cbl"})
    assert not err and len(json.loads(text)["programs"]) == 1


@pytest.mark.skipif(not HAVE_TOOLCHAIN, reason="needs a Diocle venv python (DIOCLE_PYTHON), cobc 3.2 and JDK 21")
def test_verify_stored_real_sample():
    err, text = call("diocle_verify_stored", {"sample": "interest-accrual", "random": 100})
    data = json.loads(text)
    assert not err and data["failed"] == 0 and data["passed"] == data["total"] > 100 and "not a proof" in data["honestly"]
    err, text = call("diocle_verify_stored", {"sample": "display-report"})
    assert err and "no certified-java" in text


def test_type_confused_params_do_not_crash(proc):
    for method, params in (("tools/call", {"name": ["x"]}), ("tools/call", {"name": {}}), ("tools/call", {"name": "diocle_analyze", "arguments": 5}),
                           ("prompts/get", {"name": ["x"]}), ("prompts/get", {"name": {}}),
                           ("prompts/get", {"name": "explain-a-run", "arguments": []}), ("resources/read", {"uri": 5}),
                           ("resources/read", {"uri": ["a"]}), ("tools/call", {"name": "diocle_live_run", "arguments": {"run_id": 7}}),
                           ("tools/call", {"name": "diocle_explain", "arguments": {"run": {}}}),
                           ("tools/call", {"name": "diocle_analyze", "arguments": {"path": ["x"]}})):
        r = rpc(proc, method, params)
        assert "error" in r or r["result"].get("isError") is True, (method, params)
    assert rpc(proc, "ping", i=99)["result"] == {}  # still alive


def test_internal_exception_returns_32603_without_detail(proc, monkeypatch):
    monkeypatch.setattr(server, "handle", lambda m: 1 / 0)
    code = ("import sys, json; sys.path.insert(0, %r); import server; server.handle = lambda m: 1/0; sys.exit(server.main())" % str(SERVER.parent))
    p = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    r = rpc(p, "ping")
    assert r["error"]["code"] == -32603 and "division" not in json.dumps(r) and r["id"] == 1
    r = rpc(p, "ping", i=2)  # survived
    assert r["error"]["code"] == -32603
    p.stdin.close(); p.wait(timeout=5)


def test_non_object_messages_survive(proc):
    for raw in ("[]", "5", "null", '"x"', '{"jsonrpc":"2.0","method":5,"id":1}'):
        proc.stdin.write(raw + "\n"); proc.stdin.flush()
        assert "error" in json.loads(proc.stdout.readline())
    assert rpc(proc, "ping", i=3)["result"] == {}


def test_oversized_line_rejected_and_drained(proc):
    proc.stdin.write("x" * 2_500_000 + "\n"); proc.stdin.flush()
    assert json.loads(proc.stdout.readline())["error"]["code"] == -32600
    assert rpc(proc, "ping", i=4)["result"] == {}  # the rest of the line was drained, the next message is parsed


def test_resource_symlink_and_root_confinement(tmp_path, monkeypatch):
    root = tmp_path / "repo"; (root / "samples" / "s" / "src").mkdir(parents=True)
    (root / ".env").write_text("META_MODEL_API_KEY=topsecretvalue1234\n")
    (root / "samples" / "s" / "src" / "A.cbl").write_text("       PROGRAM-ID. A.\n")
    (root / "samples" / "s" / "src" / "B.cbl").symlink_to("../../../.env")
    monkeypatch.setenv("DIOCLE_REPO", str(root))
    assert "PROGRAM-ID" in server.read_resource("diocle://samples/s/src/A.cbl")["text"]
    with pytest.raises(server.ToolError):
        server.read_resource("diocle://samples/s/src/B.cbl")
    (root / "samples" / "s" / "copybooks").symlink_to(root)  # a directory symlink out of the sample is not followed either
    with pytest.raises(server.ToolError):
        server.read_resource("diocle://samples/s/copybooks/.env")


def test_redirects_are_refused():
    class R(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302); self.send_header("Location", "http://127.0.0.1:1/x"); self.end_headers()
        def log_message(self, *a): pass
    srv = HTTPServer(("127.0.0.1", 0), R); threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["DIOCLE_API_BASE"] = f"http://127.0.0.1:{srv.server_port}"
    try:
        err, text = call("diocle_live_run", {"run_id": "some-run"})
        assert err and "302" in text
    finally:
        del os.environ["DIOCLE_API_BASE"]; srv.shutdown()


def test_timeout_kills_process_group(tmp_path):
    marker = tmp_path / "alive"
    (tmp_path / "grand.py").write_text(f"import time\ntime.sleep(2)\nopen({str(marker)!r}, 'w').write('x')\n")
    (tmp_path / "child.py").write_text(f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, {str(tmp_path / 'grand.py')!r}])\ntime.sleep(30)\n")
    with pytest.raises(server.ToolError, match="timed out"):
        server.run_argv([sys.executable, str(tmp_path / "child.py")], tmp_path, dict(os.environ), 1)
    import time; time.sleep(3)
    assert not marker.exists()  # the grandchild was killed with the group


def test_install_script_update_path_with_compact_json(tmp_path):
    fake = tmp_path / "muse"
    fake.write_text('#!/bin/sh\necho "$@" >> "$CALLS"\nif [ "$1 $2" = "plugins list" ]; then echo \'{"plugins":[{"record":{"id":"diocle","enabled":true}}]}\'; fi\nexit 0\n')
    fake.chmod(0o755)
    env = {**os.environ, "MUSE": str(fake), "CALLS": str(tmp_path / "calls"), "XDG_DATA_HOME": str(tmp_path / "d"), "XDG_CONFIG_HOME": str(tmp_path / "c")}
    r = subprocess.run(["sh", str(HERE.parent / "install.sh")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    calls = (tmp_path / "calls").read_text()
    assert "plugins update diocle" in calls and "plugins install" not in calls
    assert "approve diocle:mcp_server:diocle" in r.stdout
    assert not (tmp_path / "c" / "diocle-muse" / "allow-convert").exists()
