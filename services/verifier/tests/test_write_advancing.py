"""WRITE ... ADVANCING: what GnuCOBOL writes, and that the verifier compares those bytes. No model call anywhere here.

Every COBOL program and Java class is SYNTHETIC, written in this file. GnuCOBOL 3.2 puts the advancing into the file as
bytes, on fixed-length SEQUENTIAL files too, so a whole-number-of-records check refused even byte-identical Java."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from diocle_converter.prompts import TRANSLATOR_ADVANCING
from diocle_verifier.diff import compare
from diocle_verifier.inputs import Case
from diocle_verifier.layout import Field
from diocle_verifier.runners import IBM_FLAGS, NO_FINAL_NEWLINE, read_output
from diocle_verifier.verify import passes, verify_sample

SEQ, LINE = "SEQUENTIAL", "LINE SEQUENTIAL"

# The rule the translator and the repair agent are given (diocle_converter/prompts.py), written as code.
ADVANCE = {"1": b"\n", "2": b"\n\n", "0": b"\r", "PAGE": b"\f", "TOP": b"\f", "N": b"\n\n\n"}


def by_the_rule(org: str, writes: list[tuple[str, str, str]]) -> bytes:
    """writes: (record, "" | "AFTER" | "BEFORE", advance key), ending with a CLOSE."""
    out, flag = b"", False
    for record, how, n in writes:
        data = (record.rstrip() if org == LINE else record).encode()
        if how == "AFTER":
            out += ADVANCE[n] + data
            flag = True
        elif how == "BEFORE":
            out += data + ADVANCE[n]
            flag = False
        elif org == LINE:
            out += data + b"\n"
            flag = False
        else:
            out += data
    return out + (b"\n" if flag else b"")


A, B, C = "AAAA", "BBBB", "CCCC"
FORMS = {
    "plain": [(A, "", ""), (B, "", "")],
    "nothing written": [],
    "first after 1": [(A, "AFTER", "1"), (B, "", "")],
    "first after 2": [(A, "AFTER", "2"), (B, "", "")],
    "after an item": [(A, "AFTER", "N"), (B, "", "")],
    "after 0": [(A, "AFTER", "0"), (B, "", "")],
    "after page": [(A, "AFTER", "PAGE"), (B, "", "")],
    "after a mnemonic": [(A, "AFTER", "TOP"), (B, "", "")],
    "first before 1": [(A, "BEFORE", "1"), (B, "", "")],
    "before 2": [(A, "BEFORE", "2"), (B, "", "")],
    "before 0": [(A, "BEFORE", "0"), (B, "", "")],
    "before page": [(A, "BEFORE", "PAGE"), (B, "", "")],
    "after in the middle": [(A, "", ""), (B, "AFTER", "1"), (C, "", "")],
    "every write after": [(A, "AFTER", "1"), (B, "AFTER", "1"), (C, "AFTER", "1")],
    "every write before": [(A, "BEFORE", "1"), (B, "BEFORE", "1")],
    "last write after": [(A, "", ""), (B, "AFTER", "1")],
    "after then before": [(A, "AFTER", "1"), (B, "BEFORE", "1"), (C, "", "")],
    "before then after": [(A, "BEFORE", "1"), (B, "AFTER", "1"), (C, "", "")],
    "page both ways": [(A, "", ""), (B, "AFTER", "PAGE"), (C, "BEFORE", "PAGE")],
    "trailing spaces": [("A   ", "AFTER", "1"), ("    ", "AFTER", "1"), ("B   ", "", "")],
}
CLAUSE = {"1": "ADVANCING 1 LINE", "2": "ADVANCING 2 LINES", "0": "ADVANCING 0 LINES", "PAGE": "ADVANCING PAGE",
          "TOP": "ADVANCING TOP-OF-FORM", "N": "ADVANCING N LINES"}


def _program(org: str, body: list[str]) -> str:
    organization = "\n               ORGANIZATION IS LINE SEQUENTIAL" if org == LINE else ""
    return f"""       IDENTIFICATION DIVISION.
       PROGRAM-ID. ADVFORM.
       ENVIRONMENT DIVISION.
       CONFIGURATION SECTION.
       SPECIAL-NAMES.
           C01 IS TOP-OF-FORM.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT P ASSIGN TO PRTLINE{organization}.
       DATA DIVISION.
       FILE SECTION.
       FD  P.
       01  R PIC X(4).
       WORKING-STORAGE SECTION.
       01  N PIC 9 VALUE 3.
       PROCEDURE DIVISION.
""" + "\n".join(f"           {line}" for line in body) + "\n           GOBACK.\n"


def _run_cobol(tmp_path: Path, source: str) -> bytes:
    (tmp_path / "ADVFORM.cbl").write_text(source)
    exe, out = tmp_path / "advform", tmp_path / "out.dat"
    subprocess.run(["cobc", "-x", "-std=ibm", *IBM_FLAGS, "-o", str(exe), str(tmp_path / "ADVFORM.cbl")], check=True, capture_output=True)
    subprocess.run([str(exe)], check=True, capture_output=True, env={"PATH": os.environ["PATH"], "DD_PRTLINE": str(out)}, cwd=tmp_path)
    return out.read_bytes()


def _writes_body(writes) -> list[str]:
    body = ["OPEN OUTPUT P."]
    for record, how, n in writes:
        body += [f"MOVE '{record}' TO R.", f"WRITE R {how} {CLAUSE[n]}." if how else "WRITE R."]
    return [*body, "CLOSE P."]


@pytest.mark.parametrize("org", [SEQ, LINE])
@pytest.mark.parametrize("form", FORMS)
def test_the_rule_in_the_prompts_is_what_gnucobol_writes(tmp_path, org, form):
    assert _run_cobol(tmp_path, _program(org, _writes_body(FORMS[form]))) == by_the_rule(org, FORMS[form])


@pytest.mark.parametrize("org", [SEQ, LINE])
@pytest.mark.parametrize("stop", ["STOP RUN.", "GOBACK."])
def test_a_file_the_program_leaves_open_gets_the_closing_newline_too(tmp_path, org, stop):
    body = ["OPEN OUTPUT P.", "MOVE 'AAAA' TO R.", "WRITE R AFTER ADVANCING 1 LINE.", stop]
    assert _run_cobol(tmp_path, _program(org, body)) == b"\nAAAA\n"


@pytest.mark.parametrize("org, expected", [(SEQ, b"\nAAAA\nBBBB"), (LINE, b"\nAAAA\nBBBB\n")])
def test_the_flag_starts_false_at_each_open(tmp_path, org, expected):
    body = ["OPEN OUTPUT P.", "MOVE 'AAAA' TO R.", "WRITE R AFTER ADVANCING 1 LINE.", "CLOSE P.",
            "OPEN EXTEND P.", "MOVE 'BBBB' TO R.", "WRITE R.", "CLOSE P."]
    assert _run_cobol(tmp_path, _program(org, body)) == expected


@pytest.mark.parametrize("clause, expected", [("AFTER 1", b"\nAAAA\n"), ("AFTER 2 LINES", b"\n\nAAAA\n"), ("BEFORE 1", b"AAAA\n")])
def test_the_word_advancing_is_optional(tmp_path, clause, expected):
    body = ["OPEN OUTPUT P.", "MOVE 'AAAA' TO R.", f"WRITE R {clause}.", "CLOSE P."]
    assert _run_cobol(tmp_path, _program(SEQ, body)) == expected


@pytest.mark.parametrize("org, writes, shown", [
    (SEQ, [(A, "", ""), (B, "AFTER", "1"), (C, "", "")], r"AAAA\nBBBBCCCC\n"),
    (SEQ, [(A, "AFTER", "2"), (B, "AFTER", "1")], r"\n\nAAAA\nBBBB\n"),
    (SEQ, [(A, "BEFORE", "1"), (B, "", "")], r"AAAA\nBBBB"),
    (LINE, [(A, "", ""), (B, "AFTER", "1"), (C, "", "")], r"AAAA\n\nBBBBCCCC\n"),
])
def test_the_examples_in_the_prompt_are_real_bytes(tmp_path, org, writes, shown):
    assert shown in TRANSLATOR_ADVANCING
    assert shown.replace(r"\n", "\n").encode() == _run_cobol(tmp_path, _program(org, _writes_body(writes)))


def test_linage_does_not_follow_the_rule_and_the_prompt_says_so(tmp_path):
    source = _program(SEQ, ["OPEN OUTPUT P.", "MOVE 'AAAA' TO R.", "WRITE R.", "CLOSE P."]).replace("FD  P.", "FD  P LINAGE IS 3 LINES.")
    assert _run_cobol(tmp_path, source) == b"AAAA\n"  # by the rule it would be AAAA
    assert "LINAGE" in TRANSLATOR_ADVANCING


# A whole program through the real verifier, with hand-written Java.

COBOL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ADVDEMO.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO ADVIN.
           SELECT OUT-F ASSIGN TO ADVOUT{organization}.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F RECORDING MODE F.
       01  IN-REC.
           05  IN-CODE PIC X(4).
           05  IN-AMT  PIC 9(4).
       FD  OUT-F.
       01  OUT-REC PIC X(8).
       WORKING-STORAGE SECTION.
       01  WS-EOF  PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT IN-F OUTPUT OUT-F.
           MOVE 'TITLE   ' TO OUT-REC.
           WRITE OUT-REC.
           MOVE 'HEADING ' TO OUT-REC.
           WRITE OUT-REC AFTER ADVANCING {advance}.
           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-F
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END
                       MOVE IN-REC TO OUT-REC
                       WRITE OUT-REC
               END-READ
           END-PERFORM.
           MOVE 'TOTAL   ' TO OUT-REC.
           WRITE OUT-REC BEFORE ADVANCING 1 LINE.
           MOVE 'END     ' TO OUT-REC.
           WRITE OUT-REC AFTER ADVANCING 1 LINE.
           CLOSE IN-F OUT-F.
           GOBACK.
"""

JAVA = """import java.io.*; import java.nio.file.*;
public class Advdemo {
    public static void main(String[] a) throws Exception {
        byte[] in = Files.readAllBytes(Path.of(System.getenv("DD_ADVIN")));
        try (OutputStream o = new BufferedOutputStream(Files.newOutputStream(Path.of(System.getenv("DD_ADVOUT"))))) {
            %s
        }
    }
    static void w(OutputStream o, String s) throws IOException { o.write(s.getBytes("ISO-8859-1")); }
    static String rec(byte[] in, int i) throws IOException { return new String(in, i, 8, "ISO-8859-1"); }
}
"""
LOOP_FIXED = 'for (int i = 0; i + 8 <= in.length; i += 8) w(o, rec(in, i));'
LOOP_LINE = 'for (int i = 0; i + 8 <= in.length; i += 8) w(o, rec(in, i).stripTrailing() + "\\n");'
CORRECT = {SEQ: 'w(o, "TITLE   "); w(o, "%sHEADING "); ' + LOOP_FIXED + ' w(o, "TOTAL   \\n"); w(o, "\\nEND     \\n");',
           LINE: 'w(o, "TITLE\\n"); w(o, "%sHEADING"); ' + LOOP_LINE + ' w(o, "TOTAL\\n"); w(o, "\\nEND\\n");'}
IGNORES_THE_NEWLINES = {SEQ: 'w(o, "TITLE   "); w(o, "HEADING "); ' + LOOP_FIXED + ' w(o, "TOTAL   "); w(o, "END     ");',
                        LINE: 'w(o, "TITLE\\n"); w(o, "HEADING\\n"); ' + LOOP_LINE + ' w(o, "TOTAL\\n"); w(o, "END\\n");'}


def _sample(root: Path, org: str, advance: str = "1 LINE", name: str = "s") -> Path:
    sample = root / name
    (sample / "src").mkdir(parents=True)
    (sample / "copybooks").mkdir()
    organization = "\n               ORGANIZATION IS LINE SEQUENTIAL" if org == LINE else ""
    (sample / "src" / "ADVDEMO.cbl").write_text(COBOL.format(organization=organization, advance=advance))
    out_format = "fixed" if org == SEQ else "line"
    (sample / "sample.json").write_text(json.dumps({
        "name": name, "program": "ADVDEMO", "source": "src/ADVDEMO.cbl", "modules": [], "copybookDir": "copybooks",
        "dd": {"input": "ADVIN", "output": "ADVOUT"}, "collation": "ascii",
        "javaConversion": {"dir": "java", "mainClass": "Advdemo"},
        "layouts": {"input": {"record": "IN-REC", "format": "fixed", "fields": [
                        {"name": "IN-CODE", "kind": "alnum", "length": 4},
                        {"name": "IN-AMT", "kind": "numeric", "digits": 4, "scale": 0, "signed": False}]},
                    "output": {"record": "OUT-REC", "format": out_format, "fields": [{"name": "OUT-REC", "kind": "alnum", "length": 8}]}}}))
    return sample


def _java(root: Path, body: str) -> Path:
    java = root / "java"
    java.mkdir(parents=True)
    (java / "Advdemo.java").write_text(JAVA % body)
    return java


def _check(tmp_path: Path, org: str, body: str, advance: str = "1 LINE") -> dict:
    return verify_sample(_sample(tmp_path, org, advance), _java(tmp_path / "j", body), seed=7, random_count=40)


@pytest.mark.parametrize("org", [SEQ, LINE])
def test_correct_java_certifies_through_the_real_verifier(tmp_path, org):
    report = _check(tmp_path, org, CORRECT[org] % "\\n")
    assert passes(report), [r.get("diff") for r in report["results"] if not r["match"]][:3] or report["runs"]["converted"]["stderr"]
    assert report["summary"]["failed"] == 0 and report["summary"]["total"] > 40


@pytest.mark.parametrize("org", [SEQ, LINE])
def test_java_that_ignores_the_newlines_fails(tmp_path, org):
    report = _check(tmp_path, org, IGNORES_THE_NEWLINES[org])
    assert not passes(report) and report["summary"]["failed"] > 0


@pytest.mark.parametrize("org", [SEQ, LINE])
def test_java_missing_only_the_closing_newline_fails(tmp_path, org):
    body = CORRECT[org] % "\\n"
    assert not passes(_check(tmp_path, org, body[: body.rindex('\\n");')] + '");'))


@pytest.mark.parametrize("org", [SEQ, LINE])
def test_java_writing_a_newline_where_gnucobol_wrote_a_form_feed_fails(tmp_path, org):
    """A form feed reads as a line break to str.splitlines, so this certified on LINE SEQUENTIAL before."""
    good = _check(tmp_path / "good", org, CORRECT[org] % "\\f", advance="PAGE")
    assert passes(good), [r.get("diff") for r in good["results"] if not r["match"]][:3]
    assert not passes(_check(tmp_path / "bad", org, CORRECT[org] % "\\n", advance="PAGE"))


@pytest.mark.parametrize("org", [SEQ, LINE])
def test_one_wrong_record_byte_still_fails(tmp_path, org):
    body = (CORRECT[org] % "\\n").replace("END", "ENX")
    assert not passes(_check(tmp_path, org, body))


# The comparison itself, on records.

FIELDS = [Field("REC", "alnum", 8)]


def _one(o, c, fmt):
    return compare([], [o], [c], FIELDS, fmt)[0]


def test_identical_bytes_of_any_length_match_and_only_those():
    assert _one(" \n", " \n", "fixed")["match"]
    tail = _one(" \n", " ", "fixed")
    assert not tail["match"] and "does not end on a whole record" in tail["diff"] and r"' \n'" in tail["diff"]
    assert not _one("ABCDEFGH", "ABCDEFG", "fixed")["match"]  # the original's record is whole: an overflow or a short write
    assert not _one("ABC", "ABCDEFGH", "fixed")["match"]


def test_a_line_longer_than_the_record_matches_only_if_both_sides_wrote_it():
    assert _one("AAAABBBBCCCC", "AAAABBBBCCCC", "line")["match"]  # AFTER then plain WRITE on LINE SEQUENTIAL runs records together
    assert not _one("AAAABBBBCCCC", "AAAABBBBCCCX", "line")["match"]
    too_long = _one("ABC", "ABC        ", "line")  # trailing spaces past the record are not what a COBOL writer leaves
    assert not too_long["match"] and "overflowed" in too_long["diff"]


def test_output_lines_end_at_a_newline_byte_and_nothing_else(tmp_path):
    path = tmp_path / "out"
    path.write_bytes(b"AAAA\n\x0cBBBB\rCCCC\x85\n")
    assert read_output(path) == ["AAAA", "\x0cBBBB\rCCCC\x85"]
    path.write_bytes(b"")
    assert read_output(path) == []
    assert read_output(tmp_path / "missing") == []


def test_a_last_line_with_no_newline_is_compared_and_named(tmp_path):
    path = tmp_path / "out"
    path.write_bytes(b"AAAA\nBBBB")
    assert read_output(path) == ["AAAA", "BBBB", NO_FINAL_NEWLINE]
    original, converted = ["AAAA", "BBBB"], read_output(path)
    results = compare([Case("c", "random", "x")], original, converted, FIELDS, "line")
    assert [r["match"] for r in results] == [True, True, False]
    assert "the converted file has no newline after its last record" in results[-1]["diff"]
