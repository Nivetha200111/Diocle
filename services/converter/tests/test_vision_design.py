"""Second reviewer round on the printout intake: opt-in execution, stricter scan, stdout-only originals, odd inputs.
Scripted model; real cobc / sandbox-exec where marked."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from diocle_converter.vision import layout_problem, sandbox_available, sandbox_profile, scan_transcription, transcribe
from test_vision import LOYALTY, OK, needs_cobc, setup, valid

ORIGINAL = (LOYALTY / "src" / "LOYWAIVE.cbl").read_text()


def fence(text):
    return f"```cobol\n{text}```"


def refused(tmp_path, text, **kw):
    img, settings, client, sdk = setup(tmp_path, [fence(text)])
    called = []
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, against=LOYALTY,
                        check=lambda s, c: called.append(1) or OK(s, c), diff=lambda *a, **k: called.append("diff"),
                        run_model_code=True, log=lambda m: None, **kw)
    assert record["status"] == "refused" and called == [] and record["source"] is None, record["reason"]
    assert not (tmp_path / "out" / "src").exists()
    valid(record)
    return record["reason"]


def test_free_format_bypass_is_refused(tmp_path):
    bad = ('>>SOURCE FORMAT IS FREE\nIDENTIFICATION DIVISION.\nPROGRAM-ID. EVIL.\nPROCEDURE DIVISION.\n'
           'IF ABC*2 > 0 CALL WS-P USING "echo hi" END-CALL END-IF.\nSTOP RUN.\n')
    assert "directive" in refused(tmp_path, bad)


def test_free_format_without_a_directive_is_refused(tmp_path):
    bad = 'IDENTIFICATION DIVISION.\nPROGRAM-ID. EVIL.\nPROCEDURE DIVISION.\nIF ABC*2 > 0 CALL WS-P USING "echo hi" END-CALL END-IF.\n'
    assert "not fixed format" in refused(tmp_path, bad)


@pytest.mark.parametrize("text,word", [
    ("       IDENTIFICATION DIVISION.\n       >>SOURCE FORMAT IS FREE\n", "directive"),
    ("       IDENTIFICATION DIVISION.\n      $ SET SOURCEFORMAT\"FREE\"\n", "directive"),
    ("       IDENTIFICATION DIVISION.\n\tPROGRAM-ID. TABBED.\n", "tabs"),
    ("       IDENTIFICATION DIVISION.\n      xPROGRAM-ID. BAD.\n", "column 7"),
    ("       IDENTIFICATION DIVISION.\n" + " " * 7 + "X" * 70 + "OVERFLOW\n", "after column 72"),
])
def test_layout_refusals(text, word):
    assert word in layout_problem(text)


def test_original_passes_the_layout_check():
    assert layout_problem(ORIGINAL) is None
    assert scan_transcription(ORIGINAL, dd_names={"LOYIN", "LOYOUT"}, copybooks={"LOYIN", "LOYOUT"}) is None


@pytest.mark.parametrize("old,new,word", [
    ("ASSIGN TO LOYOUT", "ASSIGN TO '/tmp/evil.out'", "ASSIGN TO"),
    ("ASSIGN TO LOYOUT", "ASSIGN TO ../../etc/passwd", "ASSIGN TO"),
    ("ASSIGN TO LOYOUT", "ASSIGN TO OTHERDD", "ASSIGN TO"),
    ("COPY LOYOUT.", "COPY SECRETS.", "COPY"),
    ("COPY LOYOUT.", "COPY '/etc/hosts'.", "COPY"),
])
def test_assign_and_copy_are_limited_to_the_originals_names(tmp_path, old, new, word):
    assert ORIGINAL.count(old) == 1
    assert word in refused(tmp_path, ORIGINAL.replace(old, new))


def test_default_never_executes_the_transcription_and_flag_does(tmp_path):
    ran = []

    def sentinel(against, src, **k):
        ran.append(src)
        return {"against": str(against), "ran": True, "inputs": 5, "matched": 5, "mismatched": 0, "outputRecords": 5}

    img, settings, client, _ = setup(tmp_path, [fence(ORIGINAL)])
    record = transcribe(img, tmp_path / "a", settings=settings, client=client, against=LOYALTY, diff=sentinel, log=lambda m: None)
    assert ran == [] and record["status"] == "compiled-unchecked" and record["differential"] is None
    assert "needs --run-model-code" in record["reason"]
    valid(record)

    warnings = []
    img, settings, client, _ = setup(tmp_path, [fence(ORIGINAL)])
    record = transcribe(img, tmp_path / "b", settings=settings, client=client, against=LOYALTY, diff=sentinel,
                        run_model_code=True, log=warnings.append)
    assert len(ran) == 1 and record["status"] == "verified-identical"
    assert any("EXECUTED on this machine" in w for w in warnings)


def test_symlinked_out_is_refused(tmp_path):
    img, settings, client, sdk = setup(tmp_path, [fence(ORIGINAL)])
    orig = tmp_path / "orig"
    shutil.copytree(LOYALTY, orig)
    empty = tmp_path / "empty"
    empty.mkdir()
    for target, name in ((orig, "to-original"), (empty, "to-empty")):
        link = tmp_path / name
        link.symlink_to(target, target_is_directory=True)
        record = transcribe(img, link, settings=settings, client=client, against=orig, run_model_code=True, log=lambda m: None)
        assert record["status"] == "refused" and ("symbolic link" in record["reason"] or "overlaps" in record["reason"])
    assert sdk.requests == [] and not any(orig.glob("transcription.json")) and not any(empty.iterdir())


def stdout_only_sample(tmp_path, display="DISPLAY LY-ACCT ' ' LY-TENURE-MONTHS"):
    sample = tmp_path / "disp"
    shutil.copytree(LOYALTY, sample)
    shutil.rmtree(sample / "java-conversion")
    (sample / "src" / "LOYWAIVE.cbl").unlink()
    meta = json.loads((sample / "sample.json").read_text())
    meta |= {"source": "src/LOYDISP.cbl", "displayOnly": True,
             "files": [{"dd": "LOYIN", "direction": "input", "layout": meta["layouts"]["input"]}]}
    for key in ("javaConversion", "dd", "layouts"):
        meta.pop(key)
    (sample / "sample.json").write_text(json.dumps(meta))
    return sample


def disp_program(display):
    return f"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOYDISP.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LY-FILE ASSIGN TO LOYIN
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  LY-FILE.
       COPY LOYIN.
       WORKING-STORAGE SECTION.
       01  WS-EOF PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT LY-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ LY-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END {display}
               END-READ
           END-PERFORM
           CLOSE LY-FILE
           STOP RUN.
"""


@needs_cobc
def test_stdout_only_original_can_be_verified(tmp_path):
    good = "DISPLAY LY-ACCT ' ' LY-TENURE-MONTHS"
    sample = stdout_only_sample(tmp_path)
    (sample / "src" / "LOYDISP.cbl").write_text(disp_program(good))
    img, settings, client, _ = setup(tmp_path, [fence(disp_program(good))])
    record = transcribe(img, tmp_path / "ok", settings=settings, client=client, against=sample, run_model_code=True,
                        log=lambda m: None)
    d = record["differential"]
    assert record["status"] == "verified-identical", record["reason"]
    assert d["outputRecords"] == 0 and d["stdoutCompared"] is True and d["matched"] == d["inputs"] >= 1000
    valid(record)
    img, settings, client, _ = setup(tmp_path, [fence(disp_program("DISPLAY LY-ACCT"))])
    record = transcribe(img, tmp_path / "bad", settings=settings, client=client, against=sample, run_model_code=True,
                        log=lambda m: None)
    assert record["status"] == "differs" and record["differential"]["stdoutMatch"] is False


@pytest.mark.skipif(not sandbox_available(), reason="sandbox-exec is macOS only")
def test_sandbox_profile_blocks_writes_outside_the_work_dir(tmp_path):
    work = (tmp_path / "work").resolve()
    work.mkdir()
    profile = tmp_path / "p.sb"
    profile.write_text(sandbox_profile(work, Path("/usr/bin/touch")))
    inside, outside = work / "a", tmp_path.resolve() / "b"
    assert subprocess.run(["sandbox-exec", "-f", str(profile), "/usr/bin/touch", str(inside)]).returncode == 0
    assert subprocess.run(["sandbox-exec", "-f", str(profile), "/usr/bin/touch", str(outside)],
                          capture_output=True).returncode != 0
    assert inside.exists() and not outside.exists()


@needs_cobc
def test_real_run_under_the_sandbox_reports_it(tmp_path):
    img, settings, client, _ = setup(tmp_path, [fence(ORIGINAL)])
    record = transcribe(img, tmp_path / "out", settings=settings, client=client, against=LOYALTY, run_model_code=True,
                        log=lambda m: None)
    assert record["status"] == "verified-identical"
    assert record["differential"]["sandbox"] == ("sandbox-exec" if sandbox_available() else "none")


def test_copybook_dir_named_src_cannot_collide(tmp_path):
    orig = tmp_path / "orig"
    shutil.copytree(LOYALTY, orig)
    for f in (orig / "copybooks").iterdir():
        shutil.move(str(f), orig / "src" / f.name)
    shutil.rmtree(orig / "copybooks")
    meta = json.loads((orig / "sample.json").read_text())
    meta["copybookDir"] = "src"
    (orig / "sample.json").write_text(json.dumps(meta))
    fake = lambda against, src, **k: {"against": str(against), "ran": True, "inputs": 3, "matched": 3, "mismatched": 0, "outputRecords": 3}
    img, settings, client, _ = setup(tmp_path, [fence(ORIGINAL)])
    out = tmp_path / "out"
    record = transcribe(img, out, settings=settings, client=client, against=orig, check=OK, diff=fake, run_model_code=True,
                        log=lambda m: None)
    assert record["status"] == "verified-identical"
    assert (out / "src" / "LOYWAIVE.cbl").read_text() == ORIGINAL and (out / "copybooks" / "LOYIN.cpy").exists()
    assert json.loads((out / "sample.json").read_text())["copybookDir"] == "copybooks"


def test_malformed_sample_json_and_missing_cobc_are_reported(tmp_path):
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "sample.json").write_text('{"name": "x"}')
    img, settings, client, sdk = setup(tmp_path, [fence(ORIGINAL)])
    record = transcribe(img, tmp_path / "o1", settings=settings, client=client, against=bad, log=lambda m: None)
    assert record["status"] == "refused" and "unusable sample.json" in record["reason"] and (tmp_path / "o1" / "transcription.json").exists()
    assert sdk.requests == []

    def no_cobc(*a, **k):
        raise FileNotFoundError("cobc")

    img, settings, client, _ = setup(tmp_path, [fence(ORIGINAL)])
    record = transcribe(img, tmp_path / "o2", settings=settings, client=client, against=LOYALTY, check=OK, diff=no_cobc,
                        run_model_code=True, log=lambda m: None)
    assert record["status"] == "compiled-unchecked" and "FileNotFoundError" in record["reason"]
    assert (tmp_path / "o2" / "transcription.json").exists()
    valid(record)
