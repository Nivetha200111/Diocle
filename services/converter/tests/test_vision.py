"""Printout intake tests. The model is a TEST DOUBLE (scripted replies, no network, no credits); the compile and
differential gates are real GnuCOBOL runs where the test says so (skipped without cobc), otherwise injected fakes.
"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from diocle_converter import config
from diocle_converter.client import ModelClient
from diocle_converter.config import Settings
from diocle_converter.vision import (MAX_IMAGE_BYTES, ImageRejected, clean_transcription, differential, load_image,
                                     program_id, transcribe)

LOYALTY = Path(__file__).resolve().parents[3] / "samples" / "loyalty-waiver"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64
CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "transcription.schema.json"


def vision_settings(**kw):
    base = dict(mode="hosted", base_url="http://unused", api_key="test", model="muse-wonder-1.0", reasoning_effort="low",
                max_calls_per_run=3, max_calls_per_round=3, max_rounds=1)
    return Settings(**{**base, **kw})


class ScriptedSDK:
    def __init__(self, replies):
        self.script, self.requests = list(replies), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        text = self.script.pop(0)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=2000, prompt_tokens_details=None,
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=1500))
        message = SimpleNamespace(content=text)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")], usage=usage)


def setup(tmp_path, replies, **kw):
    img = tmp_path / "listing.png"
    img.write_bytes(PNG)
    settings = vision_settings(**kw)
    sdk = ScriptedSDK(replies)
    return img, settings, ModelClient(settings, _sdk=sdk), sdk


COBOL = "```cobol\n       IDENTIFICATION DIVISION.\n       PROGRAM-ID. DEMO.\n```"
OK = lambda src, cb: {"ok": True, "errors": ""}
BAD = lambda src, cb: {"ok": False, "errors": "TRANSCRIBED.cbl:2: error: syntax"}


def valid(record):
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(record, json.loads(CONTRACT.read_text()))


def test_feature_is_off_without_vision_model_id(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    for name in ("VISION_MODEL_ID", "VISION_MODEL_BASE_URL", "VISION_MODEL_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("META_MODEL_API_KEY", "k")
    monkeypatch.setenv("META_MODEL_BASE_URL", "http://x")
    assert Settings.vision_from_env() is None
    img = tmp_path / "a.png"
    img.write_bytes(PNG)
    record = transcribe(img, tmp_path / "out", settings=None)
    assert record["status"] == "refused" and "VISION_MODEL_ID" in record["reason"]
    assert record["usage"]["calls"] == 0 and (tmp_path / "out" / "transcription.json").exists()
    valid(record)


def test_vision_settings_fall_back_to_meta_host_and_key(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("VISION_MODEL_ID", "muse-wonder-1.0")
    monkeypatch.delenv("VISION_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("VISION_MODEL_API_KEY", raising=False)
    monkeypatch.setenv("META_MODEL_API_KEY", "k")
    monkeypatch.setenv("META_MODEL_BASE_URL", "http://meta")
    s = Settings.vision_from_env()
    assert (s.model, s.base_url, s.api_key, s.reasoning_effort, s.max_calls_per_run) == ("muse-wonder-1.0", "http://meta", "k", "low", 3)
    monkeypatch.setenv("VISION_MAX_CALLS", "oops")
    assert Settings.vision_from_env().max_calls_per_run == 3


def test_image_type_and_size_limits(tmp_path):
    ok_png, ok_jpg = tmp_path / "a.png", tmp_path / "b.jpg"
    ok_png.write_bytes(PNG)
    ok_jpg.write_bytes(b"\xff\xd8\xff\xe0" + b"\0" * 10)
    assert load_image(ok_png).media_type == "image/png" and load_image(ok_jpg).media_type == "image/jpeg"
    gif = tmp_path / "c.png"  # judged by bytes, not by the name
    gif.write_bytes(b"GIF89a" + b"\0" * 10)
    big = tmp_path / "big.png"
    big.write_bytes(PNG + b"\0" * MAX_IMAGE_BYTES)
    for bad in (gif, big, tmp_path / "missing.png"):
        with pytest.raises(ImageRejected):
            load_image(bad)
    record = transcribe(big, tmp_path / "out", settings=vision_settings())
    assert record["status"] == "refused" and "2 MB" in record["reason"] and record["usage"]["calls"] == 0
    valid(record)


def test_compile_failure_then_fix_sends_the_errors_back(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL, COBOL.replace("DEMO", "FIXED")])
    results = iter([BAD, OK])
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, check=lambda s, c: next(results)(s, c),
                        log=lambda m: None)
    assert record["status"] == "compiled-unchecked" and record["program"] == "FIXED"
    assert [a["compile"]["ok"] for a in record["attempts"]] == [False, True]
    retry = sdk.requests[1]["messages"]
    assert [m["role"] for m in retry] == ["user", "assistant", "user"]
    assert "syntax" in retry[2]["content"] and retry[0]["content"][1]["type"] == "image_url"
    assert (tmp_path / "out" / "src" / "FIXED.cbl").read_text().count("PROGRAM-ID. FIXED") == 1
    assert "NOT checked" in record["reason"]  # compiling is not correctness
    assert record["usage"]["calls"] == 2 and record["usage"]["estimatedCostUsd"] == pytest.approx(2 * (1000 * 4 + 2000 * 20) / 1e6)
    assert all(r["max_tokens"] for r in sdk.requests)
    valid(record)


def test_call_cap_is_hard(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL] * 5)
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, check=BAD, max_usd=10, log=lambda m: None)
    assert len(sdk.requests) == 3 and record["usage"]["calls"] == 3
    assert record["status"] == "compile-failed" and "cap" in record["reason"]
    valid(record)


def test_cost_cap_stops_before_the_call(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL])
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, check=OK, max_usd=0.01, log=lambda m: None)
    assert sdk.requests == [] and record["status"] == "no-transcription" and "cost cap" in record["reason"]
    valid(record)


def test_unpriced_model_is_refused(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL], model="some-other-vision-model")
    record = transcribe(img, tmp_path / "out", settings=settings, client=client)
    assert record["status"] == "refused" and sdk.requests == []


def test_differential_mismatch_is_reported_not_hidden(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL])
    fake = lambda against, src, **k: {"against": str(against), "ran": True, "seed": 1, "inputs": 1013, "matched": 1010,
                                      "mismatched": 3, "stdoutMatch": True, "exitCodeMatch": True, "firstMismatches": []}
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, check=OK, against=LOYALTY, run_model_code=True, diff=fake,
                        log=lambda m: None)
    assert record["status"] == "differs" and record["differential"]["mismatched"] == 3
    assert not (tmp_path / "out" / "sample.json").read_text().count("javaConversion")
    valid(record)


def test_differential_that_cannot_run_is_not_verified(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [COBOL])
    fake = lambda against, src, **k: {"against": str(against), "ran": False, "inputs": 0, "matched": 0, "mismatched": 0, "reason": "multi-file"}
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, check=OK, against=LOYALTY, run_model_code=True, diff=fake,
                        log=lambda m: None)
    assert record["status"] == "compiled-unchecked" and "multi-file" in record["reason"]
    valid(record)


def test_clean_transcription_and_program_id():
    assert clean_transcription("here:\n```cobol\n  A  \n\n B\n```\nthanks") == "  A\n\n B\n"
    assert clean_transcription("") == ""
    assert program_id("      * c\n       PROGRAM-ID. loywaive.\n") == "LOYWAIVE"


needs_cobc = pytest.mark.skipif(shutil.which("cobc") is None, reason="GnuCOBOL not installed")


@needs_cobc
def test_real_gates_identical_and_mutated(tmp_path):
    original = (LOYALTY / "src" / "LOYWAIVE.cbl").read_text()
    out = tmp_path / "out"
    img, settings, client, _ = setup(tmp_path, [f"```cobol\n{original}```"])
    record = transcribe(img, out, settings=settings, client=client, against=LOYALTY, run_model_code=True, log=lambda m: None)
    assert record["compile"]["ok"], record["compile"]
    assert record["status"] == "verified-identical" and record["differential"]["inputs"] >= 1000
    assert record["differential"]["matched"] == record["differential"]["inputs"]
    valid(record)
    # a mis-read digit (4.50 as 4.05) changes every charged account and must be caught. (A boundary-only change such as
    # "NOT < 5000.00" read as "> 5000.00" differs only at exactly 5000.00, which random inputs rarely hit: see the README.)
    mutated = original.replace("MOVE 4.50 TO LO-FEE", "MOVE 4.05 TO LO-FEE")
    assert mutated != original
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "M.cbl").write_text(mutated)
    d = differential(LOYALTY, tmp_path / "m" / "M.cbl", random_count=300)
    assert d["ran"] and d["mismatched"] > 0 and d["firstMismatches"]


@needs_cobc
def test_real_compile_gate_rejects_garbage(tmp_path):
    from diocle_converter.vision import compile_check
    bad = tmp_path / "BAD.cbl"
    bad.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. BAD.\n       PROCEDURE DIVISION.\n           MOVE TO.\n")
    result = compile_check(bad, None)
    assert result["ok"] is False and result["errors"]


def test_sandbox_flag_refuses_without_sandbox_or_original(tmp_path, monkeypatch, capsys):
    """`transcribe --sandbox` never falls back to building model-written COBOL on this machine."""
    from diocle_converter import __main__ as cli
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    img = tmp_path / "l.png"
    img.write_bytes(PNG)
    args = SimpleNamespace(image=img, out=tmp_path / "out", against=LOYALTY, run_model_code=False, sandbox=True)
    assert cli._transcribe(args) == cli.EXIT_CODES["refused"]
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://127.0.0.1:9")
    args.against = None
    assert cli._transcribe(args) == cli.EXIT_CODES["refused"]
    assert not (tmp_path / "out").exists()


@needs_cobc
def test_flow_through_the_sandbox_gates(tmp_path, monkeypatch):
    """A scripted (test-double) model reply goes through the REAL gates, run by the sandbox's handler in-process:
    the transcription is compiled and run there, and the record says so."""
    import threading
    from http.server import ThreadingHTTPServer

    from diocle_verifier import sandbox
    monkeypatch.setattr(sandbox, "_job_lock", threading.Lock())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    try:
        original = (LOYALTY / "src" / "LOYWAIVE.cbl").read_text()
        img, settings, client, _ = setup(tmp_path, [f"```cobol\n{original}```"])
        record = transcribe(img, tmp_path / "out", settings=settings, client=client, against=LOYALTY, run_model_code=True,
                            check=sandbox.remote_check(LOYALTY), diff=sandbox.remote_differential(), log=lambda m: None)
    finally:
        httpd.shutdown()
    assert record["status"] == "verified-identical" and record["differential"]["ranIn"] == "sandbox"
    assert record["differential"]["matched"] == record["differential"]["inputs"] >= 1000
    valid(record)
