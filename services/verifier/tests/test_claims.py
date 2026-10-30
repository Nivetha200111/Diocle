"""Behaviour claims (contracts/behavior-claims.schema.json): the original COBOL decides, nothing else."""

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import jsonschema
import pytest

from diocle_verifier import claims, sandbox
from diocle_verifier.layout import load_fields

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
CONTRACT = json.loads((ROOT / "contracts" / "behavior-claims.schema.json").read_text())
META = json.loads((SAMPLE / "sample.json").read_text())
OUT = load_fields(META["layouts"]["output"])

# TIEPOS: 365.00 at 0.0001 for 50 days is exactly a 0.005 tie, rounded away from zero to 0.01 (GnuCOBOL says so).
TIE = "TIEPOS    +0000003650000001050S"


def run(records):
    [r] = claims.run_original(SAMPLE, [{"id": "e1", "records": records}])
    return r


def valid_document():
    return {
        "version": "0.1", "program": "INTACCR", "model": "a-model", "checkedWith": claims.CHECKED_WITH,
        "summary": {"claims": 1, "confirmed": 0, "refuted": 1, "unchecked": 0, "examplesRun": 1},
        "claims": [{"id": "C1", "statement": "A tie is rounded away from zero.", "status": "refuted", "examples": [{
            "id": "C1-E1", "inputs": [{"ACCT-ID": "TIEPOS"}], "expected": {"records": [{"OUT-INTEREST": "0.00"}]},
            "status": "differed", "actual": {"records": [{"OUT-INTEREST": "0.01"}], "outputRecordCount": 1},
            "mismatches": [{"what": "record 1 OUT-INTEREST", "expected": "0.00", "actual": "0.01"}]}]}],
    }


def test_the_contract_accepts_a_valid_document_and_rejects_invalid_ones():
    jsonschema.validate(valid_document(), CONTRACT)
    bad_status = valid_document()
    bad_status["claims"][0]["status"] = "proven"  # the wording rule: never "proven"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_status, CONTRACT)
    no_inputs = valid_document()
    no_inputs["claims"][0]["examples"][0]["inputs"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(no_inputs, CONTRACT)
    extra = valid_document()
    extra["claims"][0]["examples"][0]["expected"]["note"] = "x"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(extra, CONTRACT)


def test_an_expectation_the_cobol_meets_is_matched():
    result = claims.judge({"records": [{"OUT-INTEREST": "0.01", "OUT-STATUS": "FE"}], "outputRecordCount": 1,
                           "stdoutContains": "READ=0000001", "returnCode": 0}, run([TIE]), OUT)
    assert result["status"] == "matched" and result["mismatches"] == []
    assert result["actual"]["records"][0]["OUT-FEE"] == "0.95"


def test_numbers_compare_by_value_and_text_ignores_trailing_spaces():
    result = claims.judge({"records": [{"OUT-INTEREST": "+0.010", "OUT-ACCT-ID": "TIEPOS   "}]}, run([TIE]), OUT)
    assert result["status"] == "matched"


def test_a_wrong_expectation_is_differed_and_keeps_the_actual_value():
    result = claims.judge({"records": [{"OUT-INTEREST": "0.00"}], "returnCode": 4}, run([TIE]), OUT)
    assert result["status"] == "differed"
    assert {"what": "record 1 OUT-INTEREST", "expected": "0.00", "actual": "0.01"} in result["mismatches"]
    assert {"what": "return code", "expected": "4", "actual": "0"} in result["mismatches"]


def test_expecting_more_records_than_the_program_wrote_differs():
    result = claims.judge({"records": [{"OUT-STATUS": "FE"}, {"OUT-STATUS": "OK"}]}, run([TIE]), OUT)
    assert result["status"] == "differed" and result["mismatches"][0]["what"] == "record 2"


def test_expectations_that_cannot_be_judged_are_unchecked_not_guessed():
    for expected, why in (({"records": [{"NO-SUCH-FIELD": "1"}]}, "not a field"),
                          ({"records": [{"OUT-FEE": "lots"}]}, "not a number"),
                          ({"records": [{"OUT-FEE": 1}]}, "not a string"),
                          ({}, "states no expected output")):
        result = claims.judge(expected, run([TIE]), OUT)
        assert result["status"] == "unchecked" and why in result["reason"] and result["actual"] is not None  # it ran


def test_a_program_that_did_not_run_leaves_the_example_unchecked(monkeypatch, tmp_path):
    result = claims.judge({"records": [{"OUT-FEE": "0.95"}]},
                          {"id": "e", "ran": False, "records": [], "stdout": "", "returnCode": None,
                           "error": "the original COBOL did not compile under GnuCOBOL"}, OUT)
    assert result["status"] == "unchecked" and "did not compile" in result["reason"]
    broken = tmp_path / "s"
    broken.mkdir()
    meta = {**META, "source": "src/BAD.cbl", "copybookDir": "cpy"}
    (broken / "sample.json").write_text(json.dumps(meta))
    (broken / "src").mkdir()
    (broken / "src" / "BAD.cbl").write_text("       THIS IS NOT COBOL\n")
    (broken / "cpy").mkdir()
    [r] = claims.run_original(broken, [{"id": "x", "records": [TIE]}])
    assert r["ran"] is False and "did not compile" in r["error"]


def test_a_program_that_hangs_is_cut_off(monkeypatch):
    import subprocess

    def hang(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)

    monkeypatch.setattr(claims, "_exec", hang)
    [r] = claims.run_original(SAMPLE, [{"id": "x", "records": [TIE]}])
    assert r["ran"] is False and "did not finish" in r["error"]


def test_claim_status_needs_every_example_to_match():
    assert claims.claim_status(["matched", "matched"]) == "confirmed"
    assert claims.claim_status(["matched", "differed", "unchecked"]) == "refuted"
    assert claims.claim_status(["matched", "unchecked"]) == "unchecked"
    assert claims.claim_status([]) == "unchecked"


def test_multi_file_programs_are_not_supported():
    assert claims.unsupported({"files": [{"dd": "A", "direction": "input"}, {"dd": "B", "direction": "input"},
                                         {"dd": "C", "direction": "output"}]})
    assert claims.unsupported(META) is None


def test_the_sandbox_path_gives_the_same_answer_as_the_local_one(monkeypatch):
    local = claims.run_original(SAMPLE, [{"id": "e1", "records": [TIE]}])
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(sandbox, "_job_lock", threading.Lock())
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    try:
        assert claims.run_original(SAMPLE, [{"id": "e1", "records": [TIE]}]) == local
    finally:
        httpd.shutdown()


# --- reviewer fixes: a clean run and a real comparison are needed before MATCHED -------------------------------

def fake_run(**over):
    base = {"id": "e", "ran": True, "records": ["TIEPOS    +000000001+0000095+00000036406FE"], "recordCount": 1,
            "stdout": "", "stderr": "", "returnCode": 0, "error": ""}
    return {**base, **over}


def test_a_crash_or_non_zero_return_code_is_never_confirmed_unless_the_example_expects_it():
    expected = {"records": [{"OUT-INTEREST": "0.01"}]}
    crashed = claims.judge(expected, fake_run(returnCode=-11, stderr="segmentation fault\nsecond line"), OUT)
    assert crashed["status"] == "unchecked" and "return code -11" in crashed["reason"] and "\n" not in crashed["reason"]
    assert crashed["actual"] is not None  # it ran, so it counts as run
    rc16 = claims.judge(expected, fake_run(returnCode=16), OUT)
    assert rc16["status"] == "unchecked"
    stated = claims.judge({**expected, "returnCode": 16}, fake_run(returnCode=16), OUT)
    assert stated["status"] == "matched"
    assert claims.judge({**expected, "returnCode": 0}, fake_run(returnCode=16), OUT)["status"] == "differed"


def test_a_weak_expectation_is_unchecked_not_matched():
    for weak in ({"outputRecordCount": 1}, {"returnCode": 0}, {"outputRecordCount": 1, "returnCode": 0}):
        got = claims.judge(weak, fake_run(), OUT)
        assert got["status"] == "unchecked" and "weak expectation" in got["reason"], weak
    assert claims.judge({"outputRecordCount": 3}, fake_run(), OUT)["status"] == "differed"  # a wrong count is still caught
    assert claims.judge({"stdoutContains": "READ"}, fake_run(stdout="INTACCR READ=1"), OUT)["status"] == "matched"


def test_zero_is_a_real_value_not_a_missing_one():
    assert claims.judge({"records": [{"OUT-STATUS": "FE"}], "outputRecordCount": 0}, fake_run(), OUT)["status"] == "differed"


def test_stdout_is_judged_on_the_whole_capture_not_the_displayed_part():
    long_out = "x" * 5000 + "NEEDLE"
    got = claims.judge({"stdoutContains": "NEEDLE"}, fake_run(stdout=long_out), OUT)
    assert got["status"] == "matched" and len(got["actual"]["stdout"]) == claims.MAX_STDOUT


def test_a_runaway_output_is_capped_but_counted(tmp_path):
    lines = [f"R{i:09d}" for i in range(500)]
    run = fake_run(records=lines[: claims.MAX_RECORDS], recordCount=500)
    got = claims.judge({"records": [{"OUT-STATUS": "FE"}], "outputRecordCount": 500}, run, OUT)
    assert got["actual"]["outputRecordCount"] == 500 and len(got["actual"]["records"]) <= 5


def test_examples_that_ran_are_counted_even_when_they_could_not_be_judged():
    ex = {"id": "x", "inputs": [{}], "expected": {}, "status": "unchecked", "actual": claims.judge({"outputRecordCount": 1}, fake_run(), OUT)["actual"]}
    nope = {"id": "y", "inputs": [{}], "expected": {}, "status": "unchecked"}
    assert claims.summarize([{"status": "unchecked", "examples": [ex, nope]}])["examplesRun"] == 1


def test_a_busy_sandbox_gives_up_after_the_short_claims_wait(monkeypatch):
    import io
    import urllib.error

    def busy(*a, **k):
        raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"busy"))

    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("DIOCLE_CLAIMS_WAIT", "0")
    monkeypatch.setattr(sandbox.urllib.request, "urlopen", busy)
    with pytest.raises(sandbox.Busy):
        claims.run_original(SAMPLE, [{"id": "e1", "records": [TIE]}])


def test_the_sandbox_refuses_oversized_or_non_latin1_records(monkeypatch):
    monkeypatch.setattr(sandbox, "_job_lock", threading.Lock())
    import base64
    bundle = base64.b64encode(sandbox.pack(SAMPLE, None)).decode()
    for bad in ("x" * 5000, "☃"):
        with pytest.raises(ValueError, match="at most 4 KB"):
            sandbox.run_job({"bundle": bundle, "examples": [{"id": "a", "records": [bad]}]}, "claims")


def test_a_record_that_would_break_line_framing_is_not_run():
    [r] = claims.run_original(SAMPLE, [{"id": "e1", "records": ["A\nB"]}])
    assert r["ran"] is False and "framing" in r["error"]


def test_a_program_that_runs_reports_the_true_record_count_and_stderr_field():
    [r] = claims.run_original(SAMPLE, [{"id": "e1", "records": [TIE, TIE]}])
    assert r["recordCount"] == 2 and len(r["records"]) == 2 and r["stderr"] == "" and r["returnCode"] == 0
