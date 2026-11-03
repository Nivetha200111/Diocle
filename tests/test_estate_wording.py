"""Where the published estate result is quoted, its wording matches the record: the fix is made, the third pass ran and is
not a blind test, its split is kept, and the two earlier passes stand."""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QUOTED = ["README.md", "apps/web/components/evidence-view.tsx", "docs/SUBMISSION_TEXT.md", "docs/BUILD_LOG.md", "docs/EVIDENCE.md", "docs/DETAILS.md"]
CAUSE_QUOTED = ["README.md", "apps/web/components/evidence-view.tsx", "docs/SUBMISSION_TEXT.md", "docs/BUILD_LOG.md"]


def _lines(path: str, phrase: str) -> list[str]:
    lines = [line for line in (REPO / path).read_text().splitlines() if phrase in line.lower()]
    assert lines, f"{path} no longer quotes {phrase}: update this test"
    return lines


@pytest.mark.parametrize("path", QUOTED)
def test_every_quote_of_the_third_pass_says_it_is_not_a_blind_test_and_keeps_the_split(path):
    for line in _lines(path, "third pass"):
        assert "not a blind test" in line
        assert "8 against a repaired copy" in line and "on fixed input" in line
        assert "has not run" not in line


@pytest.mark.parametrize("path", CAUSE_QUOTED)
def test_the_finding_still_names_both_halves_of_the_cause(path):
    text = "\n".join(_lines(path, "after advancing"))
    for stale in ("extra newlines", "Not fixed", "not fixed", "have no rule", "has no rule", "not tested program by program", "likely cause"):
        assert stale not in text, stale
    assert "refuse" in text and "no rule for it" in text


def test_the_third_pass_file_says_it_is_not_blind_and_holds_the_quoted_tally():
    third = json.loads((REPO / "eval" / "results-external-estate-third-pass.json").read_text())
    assert third["blindTest"] is False and "not a blind test" in third["pass"] and third["complete"] is True
    assert third["tally"]["certified against repaired COBOL, inputs vary, attacked"] == 8
    assert third["tally"]["certified, inputs never vary"] == 1
    assert third["tally"]["not certified"] == 3 and third["tally"]["compiled, not verified"] == 1
    estate = (REPO / "docs" / "EXTERNAL_ESTATE.md").read_text()
    assert "NOT RUN)" not in estate and "Not a blind test" in estate


def test_the_first_two_passes_are_still_the_published_files():
    first = json.loads((REPO / "eval" / "results-external-estate.json").read_text())
    second = json.loads((REPO / "eval" / "results-external-estate-second-pass.json").read_text())
    assert first["programsAccounted"] == second["programsAccounted"] == 32
    assert "blindTest" not in first and "blindTest" not in second
