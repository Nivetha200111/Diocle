"""--convert-anyway: refused programs still get a sample, carrying the refusal reason (never layouts)."""
import json
from pathlib import Path

from diocle_analyzer.analyze import analyze, write_sample

REPO = Path(__file__).resolve().parents[3] / "samples" / "convert-anyway-repo"


def test_refused_program_gets_a_non_certifiable_sample(tmp_path):
    report = analyze(REPO)
    sql = next(p for p in report["programs"] if p["name"] == "SQLRPT")
    assert not sql["convertible"]
    meta = json.loads((write_sample(REPO, report, sql, tmp_path) / "sample.json").read_text())
    assert "EXEC SQL" in meta["convertAnyway"]["reason"]
    assert "layouts" not in meta and "files" not in meta  # nothing the verifier could compare
    assert meta["source"] == "src/SQLRPT.cbl"


def test_missing_copybook_is_reported_not_fatal(tmp_path):
    (tmp_path / "repo").mkdir()
    (tmp_path / "repo" / "P.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n       COPY GONE.\n       PROCEDURE DIVISION.\n           STOP RUN.\n")
    report = analyze(tmp_path / "repo")
    p = report["programs"][0]
    meta = json.loads((write_sample(tmp_path / "repo", report, p, tmp_path / "out") / "sample.json").read_text())
    assert meta["convertAnyway"]["missingCopybooks"] == ["GONE"]
    assert "copybook(s) not found" in meta["convertAnyway"]["reason"]


def test_convertible_programs_are_unchanged(tmp_path):
    report = analyze(REPO)
    p = next(p for p in report["programs"] if p["name"] == "ADDFEE")
    meta = json.loads((write_sample(REPO, report, p, tmp_path) / "sample.json").read_text())
    assert "convertAnyway" not in meta and meta["dd"]["input"] == "ACCTIN"
