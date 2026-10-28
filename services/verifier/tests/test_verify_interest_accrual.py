"""End-to-end: GnuCOBOL original vs converted Java on the synthetic interest-accrual sample."""

import json
import shutil
from pathlib import Path

import pytest

from diocle_verifier.verify import validate_report, verify_sample

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
REFERENCE = Path(__file__).parent / "fixtures" / "reference"

pytestmark = pytest.mark.skipif(not (shutil.which("cobc") and shutil.which("javac")), reason="needs GnuCOBOL and a JDK")


@pytest.fixture(scope="module")
def naive_report():
    return verify_sample(SAMPLE, random_count=100)


def _fixture(report, name):
    return next(r for r in report["results"] if r["inputId"] == f"fixture-{name}")


def test_faithful_conversion_passes_every_case():
    report = verify_sample(SAMPLE, REFERENCE, random_count=500)
    validate_report(report)
    assert report["summary"]["failed"] == 0
    assert report["summary"]["total"] > 500
    assert report["runs"]["stdoutMatch"]


def test_naive_conversion_fails_and_report_is_valid(naive_report):
    validate_report(naive_report)
    assert naive_report["runs"]["original"]["compiled"] and naive_report["runs"]["converted"]["compiled"]
    assert naive_report["summary"]["failed"] > 0
    assert not naive_report["runs"]["stdoutMatch"]  # COMP counter displays 10 digits in COBOL


def test_planted_traps_are_caught(naive_report):
    neg_tie = _fixture(naive_report, "tie-negative")
    assert not neg_tie["match"]
    assert {"field": "OUT-INTEREST", "original": "-0.01", "converted": "0.00"} in neg_tie["fieldDiffs"]

    truncation = _fixture(naive_report, "fee-truncation")
    assert {"field": "OUT-FEE", "original": "1.49", "converted": "1.50"} in truncation["fieldDiffs"]

    overflow = _fixture(naive_report, "fee-overflow-dodges-cap")
    assert not overflow["match"] and "overflowed its width" in overflow["diff"]

    assert any(d["field"] == "OUT-FEE" for r in naive_report["results"] for d in r["fieldDiffs"] if r["inputSource"] != "fixture")


def test_programs_under_test_do_not_inherit_secrets(monkeypatch):
    from diocle_verifier.runners import safe_env
    monkeypatch.setenv("META_MODEL_API_KEY", "should-not-leak")
    monkeypatch.setenv("COB_LIBRARY_PATH", "/x")
    env = safe_env({"DD_IN": "/tmp/in"})
    assert "META_MODEL_API_KEY" not in env and env["COB_LIBRARY_PATH"] == "/x" and env["DD_IN"] == "/tmp/in"
    assert "PATH" in env


def test_packed_binary_and_overpunch_records_are_verified_byte_for_byte():
    packed = SAMPLE.parent / "packed-posting"
    good = verify_sample(packed, Path(__file__).parent / "fixtures" / "reference", random_count=150)
    assert good["summary"]["failed"] == 0 and good["runs"]["stdoutMatch"] and good["runs"]["exitCodeMatch"]
    naive = verify_sample(packed, random_count=50)
    fields = {d["field"] for r in naive["results"] for d in r.get("fieldDiffs", [])}
    assert {"PO-INT", "PO-NEW-BAL", "PO-HEADROOM", "PO-ITEM-UNITS", "PO-REVERSAL"} <= fields


def test_corpus_records_run_as_cases(tmp_path):
    sample = tmp_path / "s"
    shutil.copytree(SAMPLE, sample)
    meta = json.loads((sample / "sample.json").read_text())
    (sample / "corpus.dat").write_text("CORPUS1   +0000012345670500030S\nCORPUS2   -0000000050000500365P\n")
    meta["corpus"] = ["corpus.dat"]
    (sample / "sample.json").write_text(json.dumps(meta))
    report = verify_sample(sample, REFERENCE, random_count=5)
    corpus = [r for r in report["results"] if r["inputSource"] == "corpus"]
    assert [r["inputId"] for r in corpus] == ["corpus-0001", "corpus-0002"] and all(r["match"] for r in corpus)


def test_multi_file_match_merge_is_verified_per_output_file():
    match = SAMPLE.parent / "account-match"
    good = verify_sample(match, REFERENCE, random_count=120)
    assert good["summary"]["failed"] == 0 and good["runs"]["exitCodeMatch"] and good["runs"]["original"]["exitCode"] == 4
    assert set(good["runs"]["files"]["outputs"]) == {"NEWMST", "EXCOUT"}
    assert {r["outputDd"] for r in good["results"]} == {"NEWMST", "EXCOUT"}
    validate_report(good)
    naive = verify_sample(match, random_count=100)  # seeded: reaches the logic bugs before the port crashes
    fields = {d["field"] for r in naive["results"] for d in r.get("fieldDiffs", [])}
    assert not naive["runs"]["exitCodeMatch"] and "EX-REASON" in fields and "NM-BALANCE" in fields
