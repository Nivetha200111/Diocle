"""Programs with no output file (compared on stdout and exit code) and files opened I-O (compared on their final
contents), proven end to end with hand-written Java fixtures: no model calls."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, write_sample
from diocle_verifier.reverify import reverify
from diocle_verifier.verify import passes, validate_report, verify_sample

ROOT = Path(__file__).resolve().parents[3]
SAMPLES = ROOT / "samples"
LEDGER, DISPLAY, CALLID = SAMPLES / "ledger-rewrite", SAMPLES / "display-report", SAMPLES / "call-identifier"


def _mutated(sample: Path, tmp: Path, old: str, new: str) -> Path:
    """A copy of the sample's Java with one edit, to prove the comparison can fail."""
    java = tmp / "java"
    shutil.copytree(sample / "java-conversion", java)
    [source] = list(java.glob("*.java"))
    text = source.read_text()
    assert old in text
    source.write_text(text.replace(old, new))
    return java


# --- (b) OPEN I-O -------------------------------------------------------------------------------------------

def test_io_file_is_seeded_updated_and_compared_on_its_final_contents():
    report = verify_sample(LEDGER)
    validate_report(report)
    assert passes(report), report["runs"]["converted"]["stderr"][-500:]
    updated = report["runs"]["files"]["updated"]["ACCTMST"]
    assert updated["seeded"] > 150 and updated["original"] == updated["converted"] == updated["seeded"]
    assert {r["outputDd"] for r in report["results"]} == {"ACCTMST"}
    assert report["summary"]["total"] == updated["seeded"] and report["runs"]["exitCodeMatch"]
    assert report["runs"]["original"]["exitCode"] == 4  # the seeded data does overdraw accounts: RETURN-CODE 4


def test_wrong_update_in_the_rewritten_file_is_caught(tmp_path):
    report = verify_sample(LEDGER, _mutated(LEDGER, tmp_path, '"2.50"', '"2.51"'))
    assert not passes(report)
    bad = [r for r in report["results"] if not r["match"]]
    assert bad and any("MST-BALANCE" in r["diff"] for r in bad)
    assert report["runs"]["stdoutMatch"]  # the DISPLAY summary is identical: only the file content tells them apart


def test_a_program_that_forgets_to_rewrite_fails(tmp_path):
    java = _mutated(LEDGER, tmp_path, "Files.write(path, data);", "")
    report = verify_sample(LEDGER, java)
    assert not passes(report)
    assert any(not r["match"] for r in report["results"])


def test_closed_accounts_stay_byte_identical_and_each_side_gets_its_own_seed_copy():
    report = verify_sample(LEDGER)
    # Both sides were handed the same seed (separate copies): a record the program leaves alone matches itself.
    assert report["runs"]["files"]["updated"]["ACCTMST"]["seeded"] == report["summary"]["total"]


# --- (a) DISPLAY only ---------------------------------------------------------------------------------------

def test_display_only_program_certifies_on_stdout_and_exit_code():
    report = verify_sample(DISPLAY)
    validate_report(report)
    assert passes(report)
    [only] = report["results"]
    assert only["inputSource"] == "stdout" and only["outputDd"] == "stdout" and only["match"]
    assert report["runs"]["stdoutCompared"] is True and report["runs"]["files"]["inputs"]["TXNIN"] > 150
    assert report["runs"]["original"]["exitCode"] == report["runs"]["converted"]["exitCode"] == 4
    assert "TXNLIST DAILY LISTING" in report["runs"]["original"]["stdout"]


def test_display_only_catches_a_stdout_difference(tmp_path):
    report = verify_sample(DISPLAY, _mutated(DISPLAY, tmp_path, '" REJECTED\\n"', '" REJECT\\n"'))
    assert not passes(report) and not report["results"][0]["match"]
    assert "stdout line" in report["results"][0]["diff"]


def test_display_only_catches_an_exit_code_difference(tmp_path):
    report = verify_sample(DISPLAY, _mutated(DISPLAY, tmp_path, "System.exit(4);", "System.exit(0);"))
    assert not passes(report)
    assert "exit code: original 4 converted 0" in report["results"][0]["diff"]
    assert report["runs"]["stdoutMatch"]


QUIET = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. QUIET.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TXN-FILE ASSIGN TO TXNIN
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  TXN-FILE.
       COPY TXNREC.
       WORKING-STORAGE SECTION.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
       01  WS-COUNT                    PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
           OPEN INPUT TXN-FILE
           PERFORM UNTIL WS-EOF-FLAG = 'Y'
               READ TXN-FILE AT END MOVE 'Y' TO WS-EOF-FLAG
               NOT AT END ADD 1 TO WS-COUNT
               END-READ
           END-PERFORM
           CLOSE TXN-FILE
           STOP RUN.
"""


def _quiet_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    shutil.copytree(DISPLAY / "copybooks", repo / "copybooks")
    (repo / "QUIET.cbl").write_text(QUIET)
    assert all(len(l) <= 72 for l in QUIET.splitlines())
    return repo


def test_program_with_no_output_and_no_display_is_still_refused(tmp_path):
    [program] = analyze(_quiet_repo(tmp_path))["programs"]
    assert not program["convertible"] and program["notConvertibleReason"] == "writes no output file to compare"
    assert "displayOnly" not in program


def test_verifier_does_not_certify_nothing_even_if_told_it_is_display_only(tmp_path):
    """Defence in depth: whatever the analyzer says, a run that printed nothing and wrote nothing cannot pass."""
    repo = _quiet_repo(tmp_path)
    java = tmp_path / "java"
    java.mkdir()
    (java / "Quiet.java").write_text("public class Quiet { public static void main(String[] a) { } }\n")
    for flag in (False, True):
        report = analyze(repo)
        [program] = report["programs"]
        program["displayOnly"] = flag  # as if an analyzer bug marked it convertible
        program["convertible"] = True
        sample = write_sample(repo, report, program, tmp_path / f"out-{flag}")
        result = verify_sample(sample, java, random_count=20)
        assert not passes(result), flag
        assert result["runs"]["original"]["compiled"], result["runs"]["original"]["stderr"][-300:]
        if flag:
            assert "printed nothing" in result["results"][0]["diff"]
        else:
            assert result["summary"]["total"] == 0


def test_sql_schema_of_an_io_file_validates_against_its_contract():
    from diocle_verifier.sqlschema import schema_report, validate_report as validate_schema
    report = schema_report(json.loads((LEDGER / "sample.json").read_text()), random_count=30)
    validate_schema(report)
    assert report["summary"]["passed"] and report["tables"][0]["direction"] == "io"


# --- (c) CALL identifier ------------------------------------------------------------------------------------

def test_call_identifier_program_links_its_module_and_certifies():
    report = verify_sample(CALLID)
    validate_report(report)
    assert passes(report) and report["summary"]["total"] > 150


# --- analyzer to sample.json to verifier agree -----------------------------------------------------------------

@pytest.mark.parametrize("sample, shape", [(LEDGER, "io"), (DISPLAY, "display")])
def test_analyzer_output_is_what_the_sample_json_and_verifier_use(sample, shape, tmp_path):
    report = analyze(sample, kind="directory")
    [program] = report["programs"]
    assert program["convertible"]
    assert bool(program.get("displayOnly")) == (shape == "display")
    written = json.loads((write_sample(sample, report, program, tmp_path) / "sample.json").read_text())
    kept = json.loads((sample / "sample.json").read_text())
    for key in ("files", "displayOnly"):
        assert written.get(key) == kept.get(key)


# --- the delivery CI path (reverify) rebuilds the same shapes from the legacy checkout ------------------------

def _delivery(tmp: Path, sample: Path, program: str, main_class: str):
    work = tmp / "legacy-work"
    (work / "cobol").mkdir(parents=True)
    shutil.copytree(sample / "copybooks", work / "copybooks")
    shutil.copy2(sample / "src" / f"{program}.cbl", work / "cobol" / f"{program}.cbl")
    git = ["git", "-C", str(work), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    subprocess.run(["git", "init", "-q", str(work)], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "legacy"], check=True)
    commit = subprocess.run(git + ["rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(tmp / "legacy.git")], check=True)
    delivery = tmp / "delivery" / "programs" / program
    shutil.copytree(sample / "java-conversion", delivery / "java")
    meta = json.loads((sample / "sample.json").read_text())
    (delivery / "sample.json").write_text(json.dumps({k: meta[k] for k in ("files", "displayOnly") if k in meta}))
    (delivery / "certificate.json").write_text(json.dumps({
        "program": program, "java": {"mainClass": main_class},
        "legacy": {"repository": str(tmp / "legacy"), "commit": commit, "path": f"cobol/{program}.cbl", "copybooks": []}}))
    return delivery.parent, str(tmp / "legacy")


@pytest.mark.parametrize("sample, program, main_class", [(LEDGER, "LDGRWRT", "LdgrWrt"), (DISPLAY, "TXNLIST", "Txnlist")])
def test_reverify_rebuilds_io_and_display_only_samples(sample, program, main_class, tmp_path):
    programs, legacy = _delivery(tmp_path, sample, program, main_class)
    [result] = reverify(programs, seed=99, random_count=60, expect_legacy=legacy)
    assert result["ok"], result
    assert result["total"] >= 1


def test_reverify_rejects_a_claimed_display_only_that_the_analyzer_does_not_derive(tmp_path):
    programs, legacy = _delivery(tmp_path, LEDGER, "LDGRWRT", "LdgrWrt")
    claimed = programs / "LDGRWRT" / "sample.json"
    meta = json.loads(claimed.read_text())
    meta["displayOnly"] = True  # a pull request cannot turn an I-O program into a stdout-only one
    claimed.write_text(json.dumps(meta))
    [result] = reverify(programs, seed=1, random_count=5, expect_legacy=legacy)
    assert not result["ok"] and "differ from what the legacy copybooks define" in result["buildError"]
