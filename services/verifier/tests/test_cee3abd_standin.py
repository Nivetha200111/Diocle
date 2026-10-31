"""Diocle's CEE3ABD stand-in (IBM LE abnormal termination): linked into the GnuCOBOL build of an original that CALLs it,
on the normal path and on the abend path, locally, through the sandbox and in the delivery CI's reverify.

The fixture (tests/fixtures/abend) is SYNTHETIC, written for these tests. The claim tested is "verified against GnuCOBOL
with Diocle's CEE3ABD stand-in", never IBM Language Environment."""
import json
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, write_sample
from diocle_verifier import sandbox
from diocle_verifier.reverify import reverify
from diocle_verifier.runners import build_cobol, build_java, run_files
from diocle_verifier.standin import STANDINS, stand_ins_for
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
