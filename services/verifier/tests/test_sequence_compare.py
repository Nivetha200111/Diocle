"""Outputs are compared as a whole sequence, byte for byte (independent review, 2026-10-28)."""

from diocle_verifier.diff import compare
from diocle_verifier.inputs import Case
from diocle_verifier.layout import Field

FIELDS = [Field("CODE", "alnum", 3), Field("AMT", "numeric", 3, digits=2, signed=True, sign="leading-separate")]


def cases(n):
    return [Case(f"case-{i}", "random", f"in{i}") for i in range(n)]


def test_aggregation_with_identical_output_matches():
    out = ["TOT+05"]
    results = compare(cases(2), out, list(out), FIELDS)  # two inputs, one summary record, same on both sides
    assert [r["match"] for r in results] == [True] and results[0]["inputSource"] == "output"


def test_fan_out_with_identical_output_matches():
    out = ["AAA+01", "BBB+02"]
    results = compare(cases(1), out, list(out), FIELDS)  # one input, two records, same on both sides
    assert [r["match"] for r in results] == [True, True]


def test_same_value_different_bytes_does_not_match():
    [r] = compare(cases(1), ["ABC+00"], ["ABC-00"], FIELDS)
    assert not r["match"] and r["fieldDiffs"][0]["note"] == "same value, different bytes"
    assert r["inputId"] == "case-0"  # one record per input: the result names its input


def test_a_missing_or_extra_record_fails():
    assert [r["match"] for r in compare(cases(2), ["TOT+05"], ["TOT+05", "TOT+05"], FIELDS)] == [True, False]
    assert [r["match"] for r in compare(cases(2), ["TOT+05", "X  +01"], ["TOT+05"], FIELDS)] == [True, False]


def test_line_records_ignore_only_trailing_spaces():
    tail_alnum = [Field("AMT", "numeric", 3, digits=2, signed=True, sign="leading-separate"), Field("CODE", "alnum", 3)]
    [r] = compare(cases(1), ["+01AB"], ["+01AB "], tail_alnum)  # the COBOL writer trimmed the trailing space
    assert r["match"]
    [r] = compare(cases(1), ["+01AB"], ["+01AB    "], tail_alnum)  # longer than the record: an overflow
    assert not r["match"] and "overflowed" in r["diff"]
