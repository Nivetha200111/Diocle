"""Compile-only check of the original: contracts/compile-check.schema.json, sandbox job POST /compile."""

import json
import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import jsonschema
import pytest

from diocle_verifier import precheck, sandbox
from diocle_verifier.precheck import CompileCheck, clean_diagnostic, compile_original, diagnostics

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
    assert str(tmp_path) not in got.message and "/" not in got.message  # paths reduced to file names
    jsonschema.validate(got.to_json(), CONTRACT)


def test_messages_keep_only_cobc_diagnostics_without_paths():
    raw = ("/var/tmp/job-abc123/sample/src/X.cbl:12: error: syntax error, unexpected ENVIRONMENT\n"
           "       4 > password=hunter2 error in line\n/etc/hosts:3: warning: whatever\n" + "x" * 5000)
    assert diagnostics(raw) == ["X.cbl:12: error: syntax error, unexpected ENVIRONMENT"]
    many = "\n".join(f"/tmp/a/b.cbl:{i}: error: e{i}" for i in range(50))
    assert len(diagnostics(many)) == 4 and len(diagnostics(many + "z" * 9000)) == 4
    assert diagnostics("just some text with error in it") == []  # no fallback to arbitrary lines
    d = diagnostics(raw)[0]
    assert clean_diagnostic(d) == d  # idempotent: the client filters the sandbox's answer again
    assert all(len(x) <= precheck.MAX_DIAGNOSTIC for x in diagnostics(many))


def test_gcc_diagnostics_are_not_cobc_diagnostics():
    assert diagnostics("foo.c:12:5: error: expected ';' before 'x'\n/tmp/a/foo.c:3:1: error: oops") == []


def test_quoted_and_odd_tokens_are_masked():
    out = diagnostics("/a/b.cbl:5: error: 'SECRET-VALUE-9' is not defined\n"
                      "/a/b.cbl:6: error: syntax error, unexpected 'hunter2 pw'\n"
                      "/a/b.cbl:7: error: syntax error, unexpected TOPSECRET-sk-ABC123, expecting ENVIRONMENT\n"
                      "/a/b.cbl:8: error: syntax error, unexpected Identifier (Area B)")
    text = " | ".join(out)
    assert "SECRET" not in text and "hunter2" not in text and "sk-ABC" not in text
    assert out[0].endswith("'...' is not defined")
    assert "unexpected ..., expecting ENVIRONMENT" in out[2]
    assert out[3].endswith("unexpected Identifier (Area B)")


def test_file_trouble_is_one_generic_reason_with_no_visitor_path():
    a = diagnostics("b.cbl:5: error: /etc/hosts: No such file or directory")
    b = diagnostics("b.cbl:5: error: /root/x: Permission denied")
    c = diagnostics("b.cbl:5: error: NOSUCH: No such file or directory")
    assert a == b == c == ["b.cbl:5: error: cannot read a COPY file"]


def test_context_lines_are_dropped_before_matching_and_nothing_is_cut_on_pipes():
    """The exact leak a reviewer reproduced: cobc echoes `    2 |        <line>`; the line is cut at ' | ' by a joined-string reader."""
    text = ("LEAK.cpy:1: error: unbalanced parentheses\n"
            "    1 |        01 FOO PIC X(.\n"
            "    2 |        q.cob:1: error: TOPSECRET-sk-ABC123 hunter2\n"
            "    3 |        01 BAR PIC X.\n"
            "       q.cob:1: error: TOPSECRET-sk-ABC123 hunter2\n"
            "q.cob:1: error: TOPSECRET-sk-ABC123 hunter2 | other:2: error: TOPSECRET\n")
    out = diagnostics(text)
    assert out[0] == "LEAK.cpy:1: error: unbalanced parentheses"
    assert "TOPSECRET" not in " ".join(out) and "hunter2" not in " ".join(out) and "sk-ABC" not in " ".join(out)


def test_the_exact_leaking_copybook_through_real_cobc(monkeypatch, tmp_path):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    sample = _copy_sample(tmp_path, "LEAK")
    (sample / "copybooks" / "LEAK.cpy").write_text(
        "       01 FOO PIC X(.\n       q.cob:1: error: TOPSECRET-sk-ABC123 hunter2\n       01 BAR PIC X.\n")
    got = compile_original(sample)
    assert "TOPSECRET" not in got.message and "hunter2" not in got.message and "sk-ABC" not in got.message
    assert got.status in ("fail", "unknown")
    jsonschema.validate(got.to_json(), CONTRACT)


def _copy_sample(tmp_path: Path, copy_target: str) -> Path:
    dest = tmp_path / "leak"
    shutil.copytree(SAMPLE, dest, ignore=shutil.ignore_patterns("java-conversion"))
    src = dest / json.loads((dest / "sample.json").read_text())["source"]
    text = src.read_text()
    src.write_text(text.replace("PROCEDURE DIVISION.", f"       COPY \"{copy_target}\".\n       PROCEDURE DIVISION.", 1))
    return dest


@pytest.mark.parametrize("absolute", [False, True])
def test_a_copied_file_never_leaks_into_the_message(monkeypatch, tmp_path, absolute):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    secret = tmp_path / "private.txt"
    secret.write_text("this line has an error and TOPSECRET-TOKEN-123 in it\nsecond TOPSECRET-TOKEN-123 line\n")
    sample = _copy_sample(tmp_path, str(secret) if absolute else "private.txt")
    if not absolute:
        (sample / "copybooks" / "private.txt").write_text(secret.read_text())
    got = compile_original(sample)
    assert "TOPSECRET" not in got.message and "hunter" not in got.message
    assert got.status in ("fail", "unknown")


def test_the_environment_case_stays_readable(monkeypatch, tmp_path):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    got = compile_original(broken_sample(tmp_path))
    assert got.status == "fail" and got.diagnostics[0].endswith("syntax error, unexpected ENVIRONMENT")


def test_a_failure_without_a_diagnostic_is_unknown_not_fail(monkeypatch):
    from diocle_verifier.runners import Run

    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    for rc, err in ((-9, ""), (1, "Killed"), (1, "gcc: fatal error: No space left on device"), (1, "Cannot allocate memory"),
                    (1, ""), (4, "cobc: something odd")):
        monkeypatch.setattr(precheck, "build_cobol", lambda *a, _rc=rc, _err=err, **k: (None, Run(False, _rc, "", _err)))
        got = compile_original(SAMPLE)
        assert got.status == "unknown", (rc, err, got)


def test_a_compile_that_runs_too_long_is_unknown_not_a_reason_to_skip(monkeypatch):
    import subprocess

    def slow(*a, **kw):
        raise subprocess.TimeoutExpired("cobc", 30)

    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    monkeypatch.setattr(precheck, "build_cobol", slow)
    got = compile_original(SAMPLE)
    assert got.status == "unknown" and "longer than" in got.message


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
    monkeypatch.setattr(sandbox, "run_job", lambda job, kind="verify": {"status": "fail", "diagnostics": ["/secret/place/x.cbl:4: error: bad 'TOPSECRET'", "   9 > x.cbl:1: error: leaked",
                                                                           "    2 |        q.cob:1: error: LEAKED", "gcc.c:1:2: error: no", 7, "y" * 9000]})
    got = compile_original(SAMPLE)
    httpd.shutdown()
    assert got.status == "fail" and got.message == "x.cbl:4: error: bad '...'"
    monkeypatch.undo()


def test_a_nonsense_answer_is_unknown(server, monkeypatch):
    monkeypatch.setattr(sandbox, "run_job", lambda job, kind="verify": {"status": "maybe"})
    assert compile_original(SAMPLE).status == "unknown"
    monkeypatch.setattr(sandbox, "run_job", lambda job, kind="verify": {"status": "fail", "diagnostics": ["4 > leaked error text"]})
    assert compile_original(SAMPLE).status == "unknown"
    monkeypatch.setattr(sandbox, "run_job", lambda job, kind="verify": {"status": "fail", "message": "a:1: error: old shape"})
    assert compile_original(SAMPLE).status == "unknown"  # a failure without a cobc diagnostic is not believed


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


def test_a_hostile_bundle_cannot_write_outside_the_job(monkeypatch):
    import base64
    import io
    import tarfile

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    monkeypatch.setattr(sandbox, "_job_lock", threading.Lock())
    with pytest.raises(RuntimeError, match="outside the destination") as e:
        sandbox.run_job({"bundle": base64.b64encode(buf.getvalue()).decode()}, "compile")
    assert not isinstance(e.value, sandbox.Busy) and "OutsideDestinationError" in str(e.value)
