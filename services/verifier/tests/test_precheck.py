"""Compile-only check of the original: contracts/compile-check.schema.json, sandbox job POST /compile."""

import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import jsonschema
import pytest

from diocle_verifier import precheck, sandbox
from diocle_verifier.precheck import CompileCheck, clean_message, compile_original

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
CONTRACT = json.loads((ROOT / "contracts" / "compile-check.schema.json").read_text())


def broken_sample(tmp_path: Path) -> Path:
    """interest-accrual with a PROGRAM-ID that has no period: IBM accepts it, GnuCOBOL -std=ibm does not."""
    dest = tmp_path / "broken"
    shutil.copytree(SAMPLE, dest, ignore=shutil.ignore_patterns("java-conversion"))
    src = dest / json.loads((dest / "sample.json").read_text())["source"]
    text = src.read_text()
    assert "PROGRAM-ID. INTACCR." in text
    src.write_text(text.replace("PROGRAM-ID. INTACCR.", "PROGRAM-ID. INTACCR"))
    return dest


def test_a_compilable_original_is_ok(monkeypatch):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    got = compile_original(SAMPLE)
    assert got.status == "ok" and got.message == ""
    jsonschema.validate(got.to_json(), CONTRACT)


def test_an_original_that_does_not_compile_says_why(monkeypatch, tmp_path):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    got = compile_original(broken_sample(tmp_path))
    assert got.status == "fail" and "error" in got.message
    assert str(tmp_path) not in got.message and "/" not in got.message.replace("|", "")  # paths reduced to file names
    jsonschema.validate(got.to_json(), CONTRACT)


def test_messages_lose_paths_and_are_bounded():
    raw = "/var/tmp/job-abc123/sample/src/X.cbl:12: error: syntax error, unexpected 'PROGRAM-ID'\n" + "x" * 5000
    msg = clean_message(raw)
    assert msg.startswith("X.cbl:12: error") and "job-abc123" not in msg and len(msg) <= precheck.MAX_MESSAGE
    many = "\n".join(f"/tmp/a/b.cbl:{i}: error: e{i}" for i in range(50))
    assert clean_message(many).count("error") == 4
    assert clean_message("sample/src/X.cbl: error: relative stays") == "sample/src/X.cbl: error: relative stays"


def test_a_compile_that_runs_too_long_fails_with_a_reason(monkeypatch):
    import subprocess

    def slow(*a, **kw):
        raise subprocess.TimeoutExpired("cobc", 30)

    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    monkeypatch.setattr(precheck, "build_cobol", slow)
    got = compile_original(SAMPLE)
    assert got.status == "fail" and "longer than" in got.message


def test_a_missing_sample_is_unknown_not_an_error(monkeypatch, tmp_path):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    assert compile_original(tmp_path).status == "unknown"


# --- through the sandbox ------------------------------------------------------------------------------------

@pytest.fixture
def server(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.delenv("DIOCLE_IN_SANDBOX", raising=False)
    yield httpd
    httpd.shutdown()


def test_the_sandbox_compiles_and_reports(server, tmp_path):
    assert compile_original(SAMPLE).status == "ok"
    got = compile_original(broken_sample(tmp_path))
    assert got.status == "fail" and "error" in got.message and str(tmp_path) not in got.message


def test_with_a_sandbox_url_nothing_compiles_in_this_process(monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("compiled in the engine process")

    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://127.0.0.1:9")  # nothing listens: unreachable
    monkeypatch.delenv("DIOCLE_IN_SANDBOX", raising=False)
    monkeypatch.setattr(precheck, "build_cobol", boom)
    monkeypatch.setattr(precheck, "compile_local", boom)
    got = compile_original(SAMPLE, wait=0)
    assert got.status == "unknown" and "sandbox" in got.message


def test_a_busy_sandbox_is_retried_then_unknown(server, monkeypatch):
    monkeypatch.setattr(sandbox, "time", __import__("time"))
    assert sandbox._job_lock.acquire(blocking=False)
    try:
        got = compile_original(SAMPLE, wait=0.2)
    finally:
        sandbox._job_lock.release()
    assert got.status == "unknown" and "busy" in got.message
    assert compile_original(SAMPLE).status == "ok"  # free again


def test_a_busy_sandbox_that_frees_up_in_time_answers(server, monkeypatch):
    monkeypatch.setattr(sandbox.time, "sleep", lambda s: sandbox._job_lock.release() if sandbox._job_lock.locked() else None)
    assert sandbox._job_lock.acquire(blocking=False)
    got = compile_original(SAMPLE, wait=30)
    assert got.status == "ok"


def test_a_lying_sandbox_answer_is_not_trusted(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    monkeypatch.setattr(sandbox, "run_job", lambda job, kind="verify": {"status": "fail", "message": "/secret/place/x.cbl: error " + "y" * 9000})
    got = compile_original(SAMPLE)
    httpd.shutdown()
    assert got.status == "fail" and got.message.startswith("x.cbl") and len(got.message) <= precheck.MAX_MESSAGE
    monkeypatch.undo()


def test_a_nonsense_answer_is_unknown(server, monkeypatch):
    monkeypatch.setattr(sandbox, "run_job", lambda job, kind="verify": {"status": "maybe"})
    assert compile_original(SAMPLE).status == "unknown"


def test_compile_jobs_have_their_own_small_limits(server):
    import base64
    import urllib.error
    import urllib.request

    big = json.dumps({"bundle": base64.b64encode(b"x" * (sandbox.MAX_COMPILE_BUNDLE * 2)).decode()}).encode()
    req = urllib.request.Request(__import__("os").environ["DIOCLE_SANDBOX_URL"] + "/compile", data=big)
    with pytest.raises(urllib.error.URLError):  # 413 sent before the body is read: the server may also reset the connection
        urllib.request.urlopen(req)
    with pytest.raises(ValueError):
        sandbox.run_job({"bundle": base64.b64encode(b"x" * (sandbox.MAX_COMPILE_BUNDLE + 1)).decode()}, "compile")
    with pytest.raises(ValueError):
        sandbox.run_job({"bundle": ""}, "shell")
    assert sandbox.COMPILE_JOB_TIMEOUT < sandbox.JOB_TIMEOUT


def test_a_hostile_bundle_cannot_write_outside_the_job():
    import base64
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(RuntimeError, match="outside the destination"):
        sandbox.run_job({"bundle": base64.b64encode(buf.getvalue()).decode()}, "compile")
