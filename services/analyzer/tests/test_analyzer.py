import json
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, validate_report, write_sample
from diocle_analyzer.cobol import parse_copybook
from diocle_analyzer.github import parse_url

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
HAND_WRITTEN = ["interest-accrual", "txn-posting", "fee-schedule", "daily-control"]


@pytest.mark.parametrize("sample", HAND_WRITTEN)
def test_derived_layouts_match_hand_written_ones(sample):
    report = analyze(SAMPLES / sample)
    validate_report(report)
    meta = json.loads((SAMPLES / sample / "sample.json").read_text())
    [program] = report["programs"]
    assert program["convertible"], program["notConvertibleReason"]
    files = {f["direction"]: f for f in program["files"]}
    assert {d: files[d]["dd"] for d in ("input", "output")} == meta["dd"]
    for direction in ("input", "output"):
        derived, expected = files[direction]["layout"], meta["layouts"][direction]
        assert derived["record"] == expected["record"]
        for got, want in zip(derived["fields"], expected["fields"], strict=True):
            # The copybook only names 88-level values; the hand-written layout may list more (INTACCR's 'S' tier).
            assert {k: v for k, v in got.items() if k != "values"} == {k: v for k, v in want.items() if k != "values"}
            assert set(got.get("values", [])) <= set(want.get("values", []))


def test_findings_name_the_paragraphs_with_legacy_arithmetic():
    findings = analyze(SAMPLES / "interest-accrual")["findings"]
    seen = {(f["paragraph"], f["category"]) for f in findings}
    assert ("3000-CALC-INTEREST", "rounding") in seen
    assert ("4000-CALC-FEE", "truncation") in seen
    assert ("4000-CALC-FEE", "overflow") in seen
    assert ("9000-TERM", "display") in seen


def test_unsupported_layouts_are_reported_not_guessed():
    packed = parse_copybook("       01  R.\n           05  AMT  PIC S9(5)V99 COMP-3.\n")
    assert packed.as_dict() is None and "packed" in packed.unsupported
    redefines = parse_copybook("       01  R.\n           05  A  PIC X(4).\n           05  B  REDEFINES A PIC 9(4).\n")
    assert redefines.as_dict() is None and "REDEFINES" in redefines.unsupported
    overpunch = parse_copybook("       01  R.\n           05  N  PIC S9(3).\n")
    assert overpunch.as_dict() is None


def test_write_sample_produces_converter_input(tmp_path):
    report = analyze(SAMPLES / "fee-schedule")
    sample = write_sample(SAMPLES / "fee-schedule", report, report["programs"][0], tmp_path)
    meta = json.loads((sample / "sample.json").read_text())
    assert meta["javaConversion"]["mainClass"] == "Feeschd" and (sample / meta["source"]).exists()
    assert sorted(p.name for p in (sample / "copybooks").iterdir()) == ["CHGREC.cpy", "FEEREC.cpy"]


def test_only_allowed_github_owners(monkeypatch):
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    assert parse_url("https://github.com/Nivetha200111/quillmark-legacy") == ("Nivetha200111", "quillmark-legacy")
    with pytest.raises(PermissionError):
        parse_url("https://github.com/someone-else/repo")
    for bad in ("http://github.com/a/b", "https://github.com/a/b/../../c", "git@github.com:a/b.git"):
        with pytest.raises((ValueError, PermissionError)):
            parse_url(bad)
