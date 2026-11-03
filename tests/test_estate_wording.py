"""Where the published estate result is quoted, its wording matches the state of the code: the fix is made, the third pass has
not run, and the two published passes stand. Nothing may quote a third-pass result."""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
QUOTED = ["README.md", "apps/web/components/evidence-view.tsx", "docs/SUBMISSION_TEXT.md", "docs/BUILD_LOG.md", "docs/HANDOFF.md"]


def _sentences(path: str) -> str:
    """The lines that quote the finding."""
    text = (REPO / path).read_text()
    lines = [line for line in text.splitlines() if "AFTER ADVANCING" in line and "11 of the 13" in line]
    assert lines, f"{path} no longer quotes the finding: update this test"
    return "\n".join(lines)


@pytest.mark.parametrize("path", QUOTED)
def test_the_finding_is_quoted_as_fixed_with_the_third_pass_not_run_and_the_passes_standing(path):
    text = _sentences(path)
    for stale in ("extra newlines", "Not fixed", "not fixed", "have no rule", "has no rule", "not tested program by program", "likely cause"):
        assert stale not in text, stale
    assert "refuse" in text and "no rule for it" in text  # both halves of the cause
    assert "ixed" in text and "has not run" in text and "stand as recorded" in text


def test_no_third_pass_result_exists_or_is_claimed_while_the_protocol_says_not_run():
    assert not (REPO / "eval" / "results-external-estate-third-pass.json").exists()
    estate = (REPO / "docs" / "EXTERNAL_ESTATE.md").read_text()
    assert "NOT RUN)" in estate and "Not a blind test" in estate


def test_the_first_two_passes_are_still_the_published_files():
    first = json.loads((REPO / "eval" / "results-external-estate.json").read_text())
    second = json.loads((REPO / "eval" / "results-external-estate-second-pass.json").read_text())
    assert first["programsAccounted"] == second["programsAccounted"] == 32
    assert "blindTest" not in first and "blindTest" not in second
