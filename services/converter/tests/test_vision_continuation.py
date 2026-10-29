"""Third reviewer round: continuation-line keyword splitting, COPY without an original, and raw compiler output."""

import json
from types import SimpleNamespace

import diocle_verifier.runners as runners
from diocle_converter.vision import compile_check, own_diagnostics, scan_transcription, transcribe
from test_vision import COBOL, setup, valid

HEAD = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. X.\n       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n"
SPLIT_COPY = HEAD + "       COP\n      -    Y \"/etc/hosts\".\n"
SPLIT_CALL = (HEAD + "       01  WS-P PIC X(8).\n       PROCEDURE DIVISION.\n           MOVE 'SYS' TO WS-P(1:3)\n"
              "           MOVE 'TEM' TO WS-P(4:3)\n           CA\n      -    LL WS-P USING 'touch pwn3'\n           STOP RUN.\n")


def test_continuation_bypasses_are_refused():
    for text in (SPLIT_COPY, SPLIT_CALL):
        reason = scan_transcription(text, dd_names={"X"}, copybooks={"CPY"})
        assert reason and "continuation" in reason
        assert scan_transcription(text)  # and without an original


def test_plain_copy_without_an_original_is_refused():
    assert "COPY" in scan_transcription(HEAD + '       COPY "/etc/hosts".\n')
    assert "COPY" in scan_transcription(HEAD + "       COPY ANYTHING.\n")
    assert scan_transcription(HEAD + "      * COPY mentioned in a comment\n") is None


def test_split_programs_never_reach_the_compiler(tmp_path):
    for n, text in enumerate((SPLIT_COPY, SPLIT_CALL)):
        img, settings, client, sdk = setup(tmp_path, [f"```cobol\n{text}```"])
        called = []
        record = transcribe(img, tmp_path / f"out{n}", settings=settings, client=client,
                            check=lambda s, c: called.append(1) or {"ok": True, "errors": ""}, log=lambda m: None)
        assert record["status"] == "refused" and called == [] and len(sdk.requests) == 1
        valid(record)


RAW = """/tmp/x/TRANSCRIBED.cbl:3: error: syntax error, unexpected 'SUPERSECRET'
    3 | SUPERSECRET=abc123
      |            ^
/etc/hosts:1: error: invalid indicator '1' at column 7
    1 | 127.0.0.1 localhost
/tmp/x/TRANSCRIBED.cbl:5: error: "TOPSECRET" is not defined
note: something else
"""


def test_own_diagnostics_keeps_only_own_error_lines_with_quotes_masked():
    out = own_diagnostics(RAW, "TRANSCRIBED.cbl")
    assert out == "TRANSCRIBED.cbl:3: error: syntax error, unexpected <text>\nTRANSCRIBED.cbl:5: error: <text> is not defined"
    for leaked in ("SUPERSECRET", "abc123", "hosts", "127.0.0.1", "TOPSECRET", "|"):
        assert leaked not in out
    assert "no diagnostics" in own_diagnostics("/etc/hosts:1: error: x\n 1 | y", "TRANSCRIBED.cbl")
    assert len(own_diagnostics("\n".join(f"T.cbl:{i}: error: m" for i in range(100)), "T.cbl")) <= 1500


def test_echoed_compiler_text_never_reaches_the_retry_prompt_or_the_record(tmp_path, monkeypatch):
    def fake_exec(cmd, **k):
        return SimpleNamespace(returncode=1, stderr=RAW.replace("/tmp/x/", str(tmp_path) + "/diocle-vision/"), stdout="")

    monkeypatch.setattr(runners, "_exec", fake_exec)
    img, settings, client, sdk = setup(tmp_path, [COBOL, COBOL])
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, log=lambda m: None)
    retry_text = json.dumps(sdk.requests[1]["messages"][2])
    stored = (tmp_path / "out" / "transcription.json").read_text()
    for text in (retry_text, stored):
        for leaked in ("SUPERSECRET", "abc123", "hosts", "127.0.0.1", "TOPSECRET"):
            assert leaked not in text
    assert "TRANSCRIBED.cbl:3: error" in retry_text and record["status"] == "compile-failed"


def test_compile_check_filters_real_cobc_output(tmp_path):
    import shutil
    if shutil.which("cobc") is None:
        return
    bad = tmp_path / "BAD.cbl"
    bad.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. BAD.\n       PROCEDURE DIVISION.\n           MOVE TO.\n")
    errors = compile_check(bad, None)["errors"]
    assert errors and all(line.startswith("BAD.cbl:") and ": error: " in line for line in errors.splitlines())
