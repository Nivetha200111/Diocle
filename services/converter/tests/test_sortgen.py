"""Deterministic SORT-step generation: no model calls, pure Python (see diocle_converter/sortgen.py).

The real proof the roadmap item asks for: generate a SORT class from the REAL SortSpec the
analyzer-agent's fixture produces (samples/account-match/jcl/SORTTXN -> SORT FIELDS=(1,8,CH,A), OPTION
EQUALS), actually compile it with javac, and run it against the real samples/account-match/jcl/SORTIN.txt
fixture -- same compile-and-run-in-test pattern test_schema.py already established for the SQL DDL round trip.
"""

import shutil
import os
import subprocess
from pathlib import Path

import pytest

from diocle_converter.sortgen import generate_sort_class


def _tool_env(**extra):
    """A small environment for running the compiled programs, but with the toolchain's own PATH, library path and JAVA_HOME
    (a bare PATH=/usr/bin picks the runner's old system Java and cannot find libcob outside the system library path)."""
    keep = {k: os.environ[k] for k in ("PATH", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "JAVA_HOME") if k in os.environ}
    return {**keep, **extra}

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
ACCOUNT_MATCH_JCL = SAMPLES / "account-match" / "jcl"

# The real parsed SortSpec for samples/account-match/jcl/SORTTXN (SORT FIELDS=(1,8,CH,A), OPTION EQUALS),
# exactly as services/analyzer/diocle_analyzer/jcl.py's parse_sort_fields() produces it -- not invented.
REAL_SORT_SPEC = {"fields": [[1, 8, "CH", "A"]], "optionEquals": True, "unsupported": None}

requires_javac = pytest.mark.skipif(shutil.which("javac") is None, reason="javac not available")


def test_generate_sort_class_rejects_an_unsupported_spec():
    with pytest.raises(ValueError, match="unsupported"):
        generate_sort_class({"fields": [], "optionEquals": False, "unsupported": "MERGE is not supported yet"},
                            "X", 19, "ascii")


def test_generate_sort_class_rejects_a_key_that_does_not_fit_the_record():
    with pytest.raises(ValueError, match="does not fit"):
        generate_sort_class({"fields": [[15, 10, "CH", "A"]], "optionEquals": False, "unsupported": None},
                            "X", 19, "ascii")


def test_generate_sort_class_rejects_an_unknown_collation():
    with pytest.raises(ValueError, match="collation"):
        generate_sort_class(REAL_SORT_SPEC, "X", 19, "klingon")


def test_generate_sort_class_composes_multiple_keys_major_to_minor():
    spec = {"fields": [[1, 4, "CH", "A"], [5, 2, "CH", "D"]], "optionEquals": False, "unsupported": None}
    source = generate_sort_class(spec, "MultiKey", 10, "ascii")
    assert "thenComparing" in source  # second key chained onto the first, in field order
    # One compareKeyBytes call per key (0,4) and (4,6), plus the single method definition that implements it.
    assert source.count("DiocleSort.compareKeyBytes(a, 0, 4") == 1
    assert source.count("DiocleSort.compareKeyBytes(a, 4, 6") == 1
    assert source.count("-(DiocleSort.compareKeyBytes(a, 4, 6") == 1  # descending key is negated


def test_generate_sort_class_emits_a_stability_note_either_way():
    with_option = generate_sort_class(REAL_SORT_SPEC, "X", 19, "ascii")
    without_option = generate_sort_class({**REAL_SORT_SPEC, "optionEquals": False}, "X", 19, "ascii")
    assert "OPTION EQUALS" in with_option
    assert "absent; stable sort used anyway" in without_option
    # Both use the same stable Collections.sort regardless -- see sortgen.py's docstring on why.
    assert "Collections.sort" in with_option and "Collections.sort" in without_option


@requires_javac
def test_sort_class_compiles_and_sorts_the_real_fixture_into_ebcdic_order(tmp_path):
    """The real proof: compile the generated class, run it on the real SORTIN.txt fixture (3 records, no
    LRECL continuation), and check the output is sorted by the 8-byte account-id key in EBCDIC order --
    not ASCII order, which would wrongly put "10000001" before any "A..." key.

    Tie/stability note: this fixture's three records ("A0000002...", "10000001...", "A0000001...") have
    three DISTINCT 8-byte keys, so it does not exercise OPTION EQUALS' tie-break behaviour. Noted here for
    the verifier-agent: a fourth record repeating an existing key (e.g. another "A0000001..." row) would be
    a good addition to a future fixture to assert input order is preserved on a tie.
    """
    source = generate_sort_class(REAL_SORT_SPEC, "Sort005Test", 19, "ebcdic")
    java_file = tmp_path / "Sort005Test.java"
    java_file.write_text(source)
    classes = tmp_path / "classes"
    classes.mkdir()
    compile_proc = subprocess.run(["javac", "-d", str(classes), str(java_file)], capture_output=True, text=True)
    assert compile_proc.returncode == 0, compile_proc.stderr

    unsorted_input = (ACCOUNT_MATCH_JCL / "SORTIN.txt").read_text()
    assert unsorted_input.splitlines() == [  # the real fixture, confirmed out of EBCDIC sequence
        "A0000002+000001000C", "10000001+000000100D", "A0000001+000000500C",
    ]

    sorted_output_path = tmp_path / "SORTOUT.txt"
    run_proc = subprocess.run(
        ["java", "-cp", str(classes), "Sort005Test", "SORTIN", "SORTOUT"],
        env={"DD_SORTIN": str(ACCOUNT_MATCH_JCL / "SORTIN.txt"), "DD_SORTOUT": str(sorted_output_path),
             **_tool_env()},
        capture_output=True, text=True,
    )
    assert run_proc.returncode == 0, run_proc.stderr

    sorted_output = sorted_output_path.read_text().splitlines()
    # EBCDIC (cp037) order: digits (0xF0-F9) sort AFTER letters (0xC1+), the opposite of ASCII, where
    # "1..." would sort first. Verified independently against Python's own cp037 codec:
    #   sorted(["A0000002","10000001","A0000001"], key=lambda s: s.encode("cp037"))
    #   == ["A0000001", "A0000002", "10000001"]
    assert sorted_output == ["A0000001+000000500C", "A0000002+000001000C", "10000001+000000100D"]
    # Stable sort: every original record reappears exactly once (no data lost or duplicated by sorting).
    assert sorted(sorted_output) == sorted(unsorted_input.splitlines())


@requires_javac
def test_sort_class_uses_ascii_order_when_collation_is_ascii(tmp_path):
    """Same records, ascii collation: "1..." sorts before "A..." (plain byte order), the opposite of the
    ebcdic test above -- proves collation actually changes the comparison, not just a label in a comment."""
    source = generate_sort_class(REAL_SORT_SPEC, "Sort005Ascii", 19, "ascii")
    java_file = tmp_path / "Sort005Ascii.java"
    java_file.write_text(source)
    classes = tmp_path / "classes"
    classes.mkdir()
    subprocess.run(["javac", "-d", str(classes), str(java_file)], check=True, capture_output=True, text=True)

    sorted_output_path = tmp_path / "SORTOUT.txt"
    subprocess.run(["java", "-cp", str(classes), "Sort005Ascii", "SORTIN", "SORTOUT"],
                   env={"DD_SORTIN": str(ACCOUNT_MATCH_JCL / "SORTIN.txt"), "DD_SORTOUT": str(sorted_output_path),
                        **_tool_env()},
                   check=True, capture_output=True, text=True)
    sorted_output = sorted_output_path.read_text().splitlines()
    assert sorted_output == ["10000001+000000100D", "A0000001+000000500C", "A0000002+000001000C"]


@requires_javac
def test_sort_class_rejects_a_record_of_the_wrong_length(tmp_path):
    source = generate_sort_class(REAL_SORT_SPEC, "Sort005Bad", 19, "ascii")
    java_file = tmp_path / "Sort005Bad.java"
    java_file.write_text(source)
    classes = tmp_path / "classes"
    classes.mkdir()
    subprocess.run(["javac", "-d", str(classes), str(java_file)], check=True, capture_output=True, text=True)

    bad_input = tmp_path / "bad.txt"
    bad_input.write_text("TOO-SHORT\n")
    run_proc = subprocess.run(["java", "-cp", str(classes), "Sort005Bad", "SORTIN", "SORTOUT"],
                              env={"DD_SORTIN": str(bad_input), "DD_SORTOUT": str(tmp_path / "out.txt"),
                                   **_tool_env()},
                              capture_output=True, text=True)
    assert run_proc.returncode != 0
    assert "LRECL mismatch" in run_proc.stderr
