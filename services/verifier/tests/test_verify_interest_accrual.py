"""End-to-end: GnuCOBOL original vs converted Java on the synthetic interest-accrual sample."""

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
