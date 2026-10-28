"""The sandbox runs only compilers or programs built under its work roots, and runners can use it transparently."""

import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_verifier import runners, sandbox


def test_check_allows_compilers_and_built_programs_only(tmp_path: Path):
    roots = [tmp_path.resolve()]
    assert sandbox.check({"cmd": ["javac", "-version"], "cwd": str(tmp_path)}, roots) is None
    assert sandbox.check({"cmd": [str(tmp_path / "prog")], "cwd": str(tmp_path)}, roots) is None
    assert "not an allowed command" in sandbox.check({"cmd": ["/bin/sh", "-c", "id"]}, roots)
    assert "not an allowed command" in sandbox.check({"cmd": [str(tmp_path / ".." / "x")]}, roots)
    assert "cwd" in sandbox.check({"cmd": ["java"], "cwd": "/etc"}, roots)
    assert sandbox.check({"cmd": "java"}, roots)


@pytest.fixture
def server(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DIOCLE_SANDBOX_ROOTS", str(tmp_path))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    yield tmp_path
    httpd.shutdown()


def test_runners_go_through_the_sandbox(server: Path, monkeypatch):
    prog = server / "prog"
    prog.write_text("#!/bin/sh\necho \"out:$DIOCLE_CLOCK:${META_MODEL_API_KEY:-none}\"\nexit 3\n")
    prog.chmod(0o755)
    monkeypatch.setenv("META_MODEL_API_KEY", "must-not-leak")
    proc = runners._exec([str(prog)], env={"DIOCLE_CLOCK": "c"}, cwd=server)
    assert (proc.returncode, proc.stdout) == (3, "out:c:none\n")


def test_sandbox_refusal_is_an_error(server: Path):
    with pytest.raises(RuntimeError, match="not an allowed command"):
        runners._exec(["/bin/sh", "-c", "id"], cwd=server)
