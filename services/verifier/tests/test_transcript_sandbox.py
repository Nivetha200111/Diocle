"""The sandbox's POST /transcript: model-written COBOL is compiled and run only inside the sandbox job."""

import shutil
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_verifier import sandbox

ORIGINAL = Path(__file__).resolve().parents[3] / "samples" / "loyalty-waiver"
needs_cobc = pytest.mark.skipif(shutil.which("cobc") is None, reason="GnuCOBOL not installed")


@pytest.fixture
def server(monkeypatch):
    monkeypatch.setattr(sandbox, "_job_lock", threading.Lock())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    yield
    httpd.shutdown()


def test_pack_carries_the_transcription_with_readable_mode(tmp_path):
    import io, tarfile
    packed = sandbox.pack(ORIGINAL, None, {"transcribed/TRANSCRIBED.cbl": b"X"})
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r:gz") as tar:
        info = tar.getmember("transcribed/TRANSCRIBED.cbl")
        assert info.mode == 0o644 and tar.extractfile(info).read() == b"X"


@needs_cobc
def test_identical_transcription_is_proven_in_the_sandbox(server):
    source = (ORIGINAL / "src" / "LOYWAIVE.cbl").read_text()
    answer = sandbox.remote_transcript(ORIGINAL, source, True, wait=5)
    assert answer["compile"]["ok"], answer["compile"]
    d = answer["differential"]
    assert d["ran"] and d["inputs"] >= 1000 and d["matched"] == d["inputs"] and d["mismatched"] == 0
    # the client wrappers vision.transcribe uses
    assert sandbox.remote_check(ORIGINAL)(Path(ORIGINAL / "src" / "LOYWAIVE.cbl"), None)["ok"]
    d2 = sandbox.remote_differential()(ORIGINAL, ORIGINAL / "src" / "LOYWAIVE.cbl")
    assert d2["ranIn"] == "sandbox" and d2["against"] == str(ORIGINAL) and d2["mismatched"] == 0


@needs_cobc
def test_a_misread_digit_differs_and_garbage_fails_to_compile(server):
    source = (ORIGINAL / "src" / "LOYWAIVE.cbl").read_text()
    mutated = source.replace("MOVE 4.50 TO LO-FEE", "MOVE 4.05 TO LO-FEE")
    assert mutated != source
    d = sandbox.remote_transcript(ORIGINAL, mutated, True, wait=5)["differential"]
    assert d["ran"] and d["mismatched"] > 0
    bad = sandbox.remote_transcript(ORIGINAL, "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. BAD.\n       PROCEDURE DIVISION.\n           MOVE TO.\n", True, wait=5)
    assert bad["compile"]["ok"] is False and bad["differential"] is None


def test_sandbox_failures_degrade_to_not_run_never_to_a_local_run(monkeypatch, tmp_path):
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://127.0.0.1:9")  # nothing listens
    src = tmp_path / "T.cbl"
    src.write_text("x")
    assert sandbox.remote_check(ORIGINAL)(src, None)["ok"] is False
    d = sandbox.remote_differential()(ORIGINAL, src)
    assert d["ran"] is False and "sandbox" in d["reason"]


def test_oversized_transcription_is_refused_before_any_request(monkeypatch):
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://127.0.0.1:9")
    with pytest.raises(ValueError):
        sandbox.remote_transcript(ORIGINAL, "A" * (sandbox.MAX_TRANSCRIPT_SOURCE + 1), True)
