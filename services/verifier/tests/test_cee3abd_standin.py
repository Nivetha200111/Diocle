"""Diocle's CEE3ABD stand-in (IBM LE abnormal termination): linked into the GnuCOBOL build of an original that CALLs it,
on the normal path and on the abend path, locally, through the sandbox and in the delivery CI's reverify.

The fixture (tests/fixtures/abend) is SYNTHETIC, written for these tests. The claim tested is "verified against GnuCOBOL
with Diocle's CEE3ABD stand-in", never IBM Language Environment."""
import json
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, write_sample
from diocle_analyzer.cobol import source_lines
from diocle_verifier import sandbox
from diocle_verifier.inputs import Case
from diocle_verifier.reverify import reverify
from diocle_verifier.runners import build_cobol, build_java, run_files
from diocle_verifier.standin import STANDINS, _code, stand_ins_for
from diocle_verifier.transcript import differential
from diocle_verifier.verify import passes, validate_report, verify_sample

FIXTURE = Path(__file__).parent / "fixtures" / "abend"
JAVA = FIXTURE / "java" / "Acctchk.java"


def _sample(tmp: Path, java: Path = JAVA) -> Path:
    report = analyze(FIXTURE)
    [program] = [p for p in report["programs"] if p["name"] == "ACCTCHK"]
    assert program["convertible"], program["notConvertibleReason"]
    assert program["standIns"] == ["CEE3ABD"]
    sample = write_sample(FIXTURE, report, program, tmp / "samples")
    (sample / "java-conversion").mkdir()
    shutil.copy2(java, sample / "java-conversion" / "Acctchk.java")
    return sample


def _ignores_abend(tmp: Path) -> Path:
    """A plausible wrong translation: CALL 'CEE3ABD' treated as a normal end of the run (exit code 0)."""
    wrong = tmp / "wrong" / "Acctchk.java"
    wrong.parent.mkdir(parents=True)
    text = JAVA.read_text()
    assert "System.exit(16);" in text
    wrong.write_text(text.replace("System.exit(16);", "System.exit(0);"))
    return wrong


def test_the_stand_in_is_shipped_and_detected():
    assert (STANDINS / "CEE3ABD.cbl").is_file()
    assert stand_ins_for([FIXTURE / "src" / "ACCTCHK.cbl"]) == ["CEE3ABD"]
    # a repository that defines its own CEE3ABD keeps it: no stand-in
    assert stand_ins_for([FIXTURE / "src" / "ACCTCHK.cbl", STANDINS / "CEE3ABD.cbl"]) == []


FREE_FORMAT = """>>SOURCE FORMAT FREE
IDENTIFICATION DIVISION.
PROGRAM-ID. FREECHK.
DATA DIVISION.
WORKING-STORAGE SECTION.
01 ABCODE PIC S9(9) BINARY VALUE 7.
01 TIMING PIC S9(9) BINARY VALUE 0.
PROCEDURE DIVISION.
DISPLAY 'BEFORE'.
CALL "CEE3ABD" USING ABCODE, TIMING.
DISPLAY 'AFTER'.
STOP RUN.
"""


def test_a_free_format_call_is_detected_and_linked_like_the_analyzer_reads_it(tmp_path):
    """A CALL in the first columns of a free-format line is outside columns 8-72, where the analyzer does see it."""
    source = tmp_path / "src" / "FREECHK.cbl"
    source.parent.mkdir()
    source.write_text(FREE_FORMAT)
    [program] = [p for p in analyze(tmp_path)["programs"] if p["name"] == "FREECHK"]
    assert program["standIns"] == ["CEE3ABD"]
    assert stand_ins_for([source]) == ["CEE3ABD"]
    work = tmp_path / "work"
    work.mkdir()
    command, failed = build_cobol(source, tmp_path, work)  # free-format main, fixed-format stand-in: linked per file
    assert failed is None, failed
    run = run_files(command, {}, {}, work, "original")
    assert run.exit_code == 16 and run.stdout == "BEFORE\n" and "CEE3ABD abend code 7" in run.stderr


def test_a_free_format_comment_or_past_column_72_is_read_correctly(tmp_path):
    commented, far, own = (tmp_path / n for n in ("c.cbl", "f.cbl", "o.cbl"))
    commented.write_text(FREE_FORMAT.replace('CALL "CEE3ABD" USING ABCODE, TIMING.', '*> CALL "CEE3ABD" USING ABCODE, TIMING.'))
    far.write_text(FREE_FORMAT.replace('CALL "CEE3ABD"', " " * 80 + 'CALL "CEE3ABD"'))  # fixed format would cut this off
    own.write_text(FREE_FORMAT.replace("PROGRAM-ID. FREECHK.", "PROGRAM-ID. CEE3ABD."))  # its own routine, at column 1
    assert stand_ins_for([commented]) == []
    assert stand_ins_for([far]) == ["CEE3ABD"]
    assert stand_ins_for([own]) == []


def test_the_source_is_read_as_the_analyzer_reads_it(tmp_path):
    """standin.py keeps its own reading (the verifier must run without the analyzer); this keeps the two in step."""
    tricky = (FREE_FORMAT + "DISPLAY '*> IN A LITERAL' *> A COMMENT\nDISPLAY 'IT''S' *> SECOND\n"
              '$SET SOMETHING\nDISPLAY "A \'B" *> THIRD\n' + "x" * 90 + "\n")
    samples = {"free.cbl": tricky, "fixed.cbl": (FIXTURE / "src" / "ACCTCHK.cbl").read_text() + "       " + "Y" * 80 + "\n"}
    for name, text in samples.items():
        path = tmp_path / name
        path.write_text(text)
        ours = [l.strip() for l in _code(path).splitlines() if l.strip()]
        assert ours == [code.strip().upper() for _, code in source_lines(text)], name


def test_verifying_does_not_need_the_analyzer():
    """scripts/quickstart.sh and the README's setup install the verifier without it: a judge's first command. test.sh's
    venvs have the analyzer, so only a blocked import shows this."""
    sample = Path(__file__).resolve().parents[3] / "samples" / "interest-accrual"
    script = ("import sys; sys.modules['diocle_analyzer'] = None\n"
              "from pathlib import Path\n"
              "from diocle_verifier.verify import passes, verify_sample\n"
              f"report = verify_sample(Path({str(sample)!r}), Path({str(sample / 'certified-java')!r}), seed=1, random_count=5)\n"
              "sys.exit(0 if passes(report) else 3)\n")
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr[-800:]


def test_normal_path_is_certified_and_the_report_states_the_stand_in(tmp_path):
    report = verify_sample(_sample(tmp_path), seed=11, random_count=80)
    validate_report(report)
    assert passes(report), report["runs"]
    assert report["runs"]["original"]["exitCode"] == 0 and report["summary"]["total"] > 80
    [standin] = report["runs"]["standIns"]
    assert standin["routine"] == "CEE3ABD" and standin["exitCode"] == 16 and "not IBM" in standin["note"]


def _both(tmp: Path, java: Path, input_text: str | None) -> tuple:
    sample = _sample(tmp, java)
    meta = json.loads((sample / "sample.json").read_text())
    work = tmp / "work"
    work.mkdir()
    cobol_cmd, failed = build_cobol(sample / meta["source"], sample / meta["copybookDir"], work)
    assert failed is None, failed
    java_cmd, failed = build_java(sample / "java-conversion", "Acctchk", work)
    assert failed is None, failed
    data = work / "in.dat"
    if input_text is not None:
        data.write_text(input_text)
    outputs = {"ACCTOUT": ("line", 0)}
    original = run_files(cobol_cmd, {"ACCTIN": data}, outputs, work, "original")
    converted = run_files(java_cmd, {"ACCTIN": data}, outputs, work, "converted")
    return original, converted


def test_abend_path_ends_with_16_and_keeps_output_written_so_far(tmp_path):
    records = "A00001S+000001050\nA00002C-000000075\n      C+000000001\nA00004S+000000002\n"
    original, converted = _both(tmp_path, JAVA, records)
    assert original.exit_code == 16, original.stderr
    assert original.stdout == "BLANK ACCOUNT ID AFTER 00002\nABENDING PROGRAM\n"
    assert original.output_files["ACCTOUT"] == ["A00001S+000001050", "A00002N-000000075"]  # closed as at STOP RUN
    assert "CEE3ABD abend code 999" in original.stderr
    assert (converted.exit_code, converted.stdout, converted.output_files) == (
        original.exit_code, original.stdout, original.output_files)


def test_open_failure_abend_like_a_9999_abend_paragraph(tmp_path):
    original, converted = _both(tmp_path, JAVA, None)  # DD_ACCTIN names a file that does not exist
    assert original.exit_code == 16 and original.stdout == "ACCTIN OPEN FAILED 35\nABENDING PROGRAM\n"
    assert "CEE3ABD abend code 101" in original.stderr
    assert (converted.exit_code, converted.stdout) == (original.exit_code, original.stdout)


def test_java_that_ignores_the_abend_is_not_certified(tmp_path):
    sample = _sample(tmp_path, _ignores_abend(tmp_path))
    meta = json.loads((sample / "sample.json").read_text())
    meta["fixtureCases"] = [{"id": "blank-id", "record": "      C+000000001"}]  # first record: the abend path
    (sample / "sample.json").write_text(json.dumps(meta))
    report = verify_sample(sample, seed=11, random_count=20)
    assert report["runs"]["original"]["exitCode"] == 16 and report["runs"]["converted"]["exitCode"] == 0
    assert not report["runs"]["exitCodeMatch"] and not passes(report)


OK, BLANK, LATER = "A00001S+000001050", "      C+000000001", "A00003S+000000002"


def _abends_on_the_second_record(sample: Path) -> Path:
    meta = json.loads((sample / "sample.json").read_text())
    meta["fixtureCases"] = [{"id": "ok", "record": OK}, {"id": "blank", "record": BLANK}, {"id": "later", "record": LATER}]
    (sample / "sample.json").write_text(json.dumps(meta))
    return sample


def test_a_run_that_ends_at_the_stand_in_part_way_is_not_certified_and_says_how_far_it_got(tmp_path):
    """A faithful Java abends at the same record, so everything compared matches, on 1 record of the 90 or so supplied:
    every input after it ran on neither side. This was certified as 1/1."""
    report = verify_sample(_abends_on_the_second_record(_sample(tmp_path)), seed=11, random_count=80)
    validate_report(report)
    runs = report["runs"]
    assert not passes(report)
    assert runs["exitCodeMatch"] and runs["stdoutMatch"] and runs["original"]["exitCode"] == 16  # both sides really agree
    ended = runs["endedAtStandIn"]
    assert (ended["routine"], ended["exitCode"], ended["abendCode"]) == ("CEE3ABD", 16, "999")
    assert ended["outputRecords"] == {"ACCTOUT": 1} and ended["inputRecords"]["ACCTIN"] > 80
    first = report["results"][0]  # first, so the run page's failing examples and the repair prompt lead with it
    assert first["inputId"] == "stand-in-end" and not first["match"] and first["diff"] == ended["reason"]
    assert "ACCTOUT 1" in first["diff"] and f"ACCTIN {ended['inputRecords']['ACCTIN']}" in first["diff"]
    assert "not a fault of the converted Java" in first["diff"]
    # Readers that add up the summary themselves (services/api/diocle_api/reverify.py) fail closed too.
    assert report["summary"] == {"total": 2, "passed": 1, "failed": 1}


def test_a_run_that_ends_at_the_stand_in_on_the_first_record_still_gives_the_reason(tmp_path):
    sample = _sample(tmp_path)
    meta = json.loads((sample / "sample.json").read_text())
    meta["fixtureCases"] = [{"id": "blank", "record": BLANK}]
    (sample / "sample.json").write_text(json.dumps(meta))
    report = verify_sample(sample, seed=11, random_count=10)
    assert not passes(report) and report["runs"]["endedAtStandIn"]["outputRecords"] == {"ACCTOUT": 0}
    assert [r["inputId"] for r in report["results"]] == ["stand-in-end"]


def test_the_multi_file_path_fails_closed_the_same_way(tmp_path):
    sample = _sample(tmp_path)
    meta = json.loads((sample / "sample.json").read_text())
    meta["displayOnly"] = True  # takes the multi-file path; the output file is still compared
    meta["fixtureFiles"] = {"ACCTIN": [OK, BLANK, LATER]}
    (sample / "sample.json").write_text(json.dumps(meta))
    report = verify_sample(sample, seed=11, random_count=30)
    validate_report(report)
    assert not passes(report) and report["runs"]["exitCodeMatch"]
    ended = report["runs"]["endedAtStandIn"]
    assert ended["outputRecords"] == {"ACCTOUT": 1} and ended["inputRecords"]["ACCTIN"] > 30
    assert report["results"][0]["inputId"] == "stand-in-end" and report["summary"]["failed"] == 1


def test_an_attack_probe_that_reaches_the_abend_is_not_a_break_and_still_certifies_nothing(tmp_path):
    """The breaker verifies with no random inputs and treats any failing result as a break of the Java. Both sides agree here."""
    report = verify_sample(_sample(tmp_path), seed=1026, random_count=0, extra_cases=[Case("breaker-1", "model", BLANK)])
    validate_report(report)
    assert all(r["match"] for r in report["results"]) and report["runs"]["endedAtStandIn"]["abendCode"] == "999"
    assert not passes(report)


def test_return_code_16_without_reaching_the_stand_in_stays_certified(tmp_path):
    """Built with the stand-in, never reached (CBACT02C-style normal path), but its own RETURN-CODE is 16: it read everything."""
    java = tmp_path / "own16" / "Acctchk.java"
    java.parent.mkdir()
    text = JAVA.read_text()
    assert text.count("        out.close();\n    }\n") == 1
    java.write_text(text.replace("        out.close();\n    }\n", "        out.close();\n        System.exit(16);\n    }\n"))
    sample = _sample(tmp_path, java)
    meta = json.loads((sample / "sample.json").read_text())
    source = sample / meta["source"]
    cobol = source.read_text()
    assert cobol.count("           STOP RUN.\n") == 1
    source.write_text(cobol.replace("           STOP RUN.\n", "           MOVE 16 TO RETURN-CODE\n           STOP RUN.\n"))
    report = verify_sample(sample, seed=11, random_count=40)
    assert passes(report), report["results"][:2]
    assert report["runs"]["original"]["exitCode"] == 16 and "endedAtStandIn" not in report["runs"]
    assert report["runs"]["standIns"][0]["routine"] == "CEE3ABD"  # still stated: it is linked


def test_a_transcription_of_a_run_that_ends_at_the_stand_in_proves_nothing(tmp_path):
    sample = _abends_on_the_second_record(_sample(tmp_path))
    meta = json.loads((sample / "sample.json").read_text())
    result = differential(sample, sample / meta["source"], random_count=20, sandbox=False)
    assert result["ran"] is False and "CEE3ABD stand-in" in result["reason"]


@pytest.fixture
def sandbox_server(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
    yield
    httpd.shutdown()


def test_the_sandbox_links_the_stand_in_too(tmp_path, sandbox_server):
    report = verify_sample(_sample(tmp_path), seed=11, random_count=30)
    assert passes(report) and report["runs"]["standIns"][0]["routine"] == "CEE3ABD"


def test_delivery_ci_reverify_links_the_stand_in(tmp_path):
    work = tmp_path / "legacy-work"
    shutil.copytree(FIXTURE / "src", work / "cobol")
    shutil.copytree(FIXTURE / "copybooks", work / "copybooks")
    git = ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "legacy"], check=True)
    commit = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(tmp_path / "legacy.git")], check=True)
    repository = str(tmp_path / "legacy")

    def delivery(name: str, java: Path) -> Path:
        program = tmp_path / name / "programs" / "ACCTCHK"
        (program / "java").mkdir(parents=True)
        shutil.copy2(java, program / "java" / "Acctchk.java")
        [derived] = analyze(work)["programs"]
        files = {f["direction"]: f for f in derived["files"]}
        (program / "sample.json").write_text(json.dumps({"dd": {d: files[d]["dd"] for d in ("input", "output")},
                                                         "layouts": {d: files[d]["layout"] for d in ("input", "output")}}))
        (program / "certificate.json").write_text(json.dumps({
            "program": "ACCTCHK", "java": {"mainClass": "Acctchk"},
            "legacy": {"repository": repository, "commit": commit, "path": "cobol/ACCTCHK.cbl",
                       "copybooks": ["copybooks/ACCTREC.cpy"]}}))
        return program.parent

    [good] = reverify(delivery("good", JAVA), seed=777, random_count=60, expect_legacy=repository)
    assert good["ok"], good
