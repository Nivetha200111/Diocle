"""DISPLAY-only programs, files opened I-O and CALL identifier resolution.

The analyzer may say "convertible" for these shapes only because services/verifier compares them (stdout and exit
code; final file contents). Every negative case here is a shape the verifier could not certify, so it must be refused.
"""
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, validate_report
from diocle_analyzer.cobol import parse_program

SAMPLES = Path(__file__).resolve().parents[3] / "samples"

HEAD = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINP.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO INDD
               ORGANIZATION IS {org}.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC.
           05  IN-ID    PIC X(4).
       WORKING-STORAGE SECTION.
{ws}
       PROCEDURE DIVISION.
{body}
           STOP RUN.
"""


def _program(body: str, ws: str = "       01  WS-X   PIC X.", org: str = "LINE SEQUENTIAL") -> str:
    return HEAD.format(body=body, ws=ws, org=org)


def _analyze(tmp_path: Path, text: str, extra: dict[str, str] | None = None) -> dict:
    for name, source in {"MAINP.cbl": text, **(extra or {})}.items():
        (tmp_path / name).write_text(source)
    return next(p for p in analyze(tmp_path)["programs"] if p["name"] == "MAINP")


SUB = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. SUBA.
       PROCEDURE DIVISION.
           GOBACK.
"""
SUB_B = SUB.replace("SUBA", "SUBB")


# --- (a) DISPLAY only --------------------------------------------------------------------------------------

def test_display_only_program_is_convertible_and_marked(tmp_path):
    p = _analyze(tmp_path, _program("           OPEN INPUT IN-F\n           DISPLAY 'HELLO'\n           CLOSE IN-F"))
    assert p["convertible"] and p["displayOnly"] is True


def test_programs_with_an_output_file_are_not_display_only():
    for sample in ("interest-accrual", "account-match", "txn-posting"):
        [p] = analyze(SAMPLES / sample)["programs"]
        assert p["convertible"] and "displayOnly" not in p


@pytest.mark.parametrize("body, why", [
    ("           OPEN INPUT IN-F\n           CLOSE IN-F", "no DISPLAY at all"),
    ("           OPEN INPUT IN-F\n           DISPLAY 'ERR' UPON SYSERR\n           CLOSE IN-F", "only stderr"),
    ("           OPEN INPUT IN-F\n           ACCEPT WS-X\n           DISPLAY WS-X\n           CLOSE IN-F", "console ACCEPT"),
])
def test_no_stdout_to_compare_or_console_input_is_refused(tmp_path, body, why):
    p = _analyze(tmp_path, _program(body))
    assert not p["convertible"], why
    assert "displayOnly" not in p


def test_usage_display_clause_is_not_a_display_statement(tmp_path):
    ws = "       01  WS-X   PIC X USAGE DISPLAY.\n       01  WS-Y   PIC 9 USAGE IS DISPLAY."
    p = _analyze(tmp_path, _program("           OPEN INPUT IN-F\n           CLOSE IN-F", ws))
    assert not p["convertible"] and p["notConvertibleReason"] == "writes no output file to compare"


def test_accept_from_date_is_fine(tmp_path):
    body = "           OPEN INPUT IN-F\n           ACCEPT WS-X FROM DATE\n           DISPLAY WS-X\n           CLOSE IN-F"
    assert _analyze(tmp_path, _program(body))["displayOnly"] is True


# --- (b) OPEN I-O ------------------------------------------------------------------------------------------

def test_open_io_is_its_own_direction():
    code = _program("           OPEN I-O IN-F\n           CLOSE IN-F", org="SEQUENTIAL")
    assert parse_program(code).directions == {"IN-F": "io"}


def test_sequential_file_opened_io_is_convertible(tmp_path):
    p = _analyze(tmp_path, _program("           OPEN I-O IN-F\n           CLOSE IN-F", org="SEQUENTIAL"))
    assert p["convertible"] and "displayOnly" not in p and [f["direction"] for f in p["files"]] == ["io"]
    validate_report(analyze(tmp_path))


@pytest.mark.parametrize("org, body, fragment", [
    ("LINE SEQUENTIAL", "           OPEN I-O IN-F\n           CLOSE IN-F", "must be ORGANIZATION SEQUENTIAL"),
    ("INDEXED", "           OPEN I-O IN-F\n           CLOSE IN-F", "keyed file"),
    ("SEQUENTIAL", "           OPEN I-O IN-F\n           CLOSE IN-F\n           OPEN INPUT IN-F", "opened I-O or never opened"),
    ("SEQUENTIAL", "           OPEN INPUT IN-F\n           CLOSE IN-F\n           OPEN I-O IN-F", "opened I-O or never opened"),
])
def test_io_shapes_the_verifier_cannot_seed_are_refused(tmp_path, org, body, fragment):
    p = _analyze(tmp_path, _program(body, org=org))
    assert not p["convertible"] and fragment in p["notConvertibleReason"]


def test_file_never_opened_is_still_refused(tmp_path):
    p = _analyze(tmp_path, _program("           DISPLAY 'X'", org="SEQUENTIAL"))
    assert not p["convertible"] and "opened I-O or never opened" in p["notConvertibleReason"]


# --- (c) CALL identifier -----------------------------------------------------------------------------------

def _call(body: str, ws: str, tmp_path: Path, extra=None) -> dict:
    full = "           OPEN INPUT IN-F\n" + body + "\n           CLOSE IN-F"
    return _analyze(tmp_path, _program(full + "\n           DISPLAY 'DONE'", ws), {"SUBA.cbl": SUB, **(extra or {})})


WS_PGM = "       01  WS-PGM   PIC X(8) VALUE 'SUBA'.\n       01  WS-X     PIC X(8)."


def test_value_clause_only(tmp_path):
    p = _call("           CALL WS-PGM", WS_PGM, tmp_path)
    assert p["convertible"] and p["resolvedCalls"] == {"WS-PGM": "SUBA"} and p["modules"] == ["SUBA.cbl"]


def test_literal_moves_agreeing_with_value_even_across_lines(tmp_path):
    body = "           MOVE\n               'SUBA'\n               TO WS-PGM\n           CALL WS-PGM USING WS-X"
    p = _call(body, WS_PGM, tmp_path)
    assert p["convertible"] and p["resolvedCalls"] == {"WS-PGM": "SUBA"}


def test_move_to_several_receivers_and_double_quotes(tmp_path):
    body = '           MOVE "SUBA" TO WS-X WS-PGM\n           CALL WS-PGM'
    assert _call(body, WS_PGM, tmp_path)["resolvedCalls"] == {"WS-PGM": "SUBA"}


def test_only_moves_without_value_clause_also_resolve(tmp_path):
    ws = "       01  WS-PGM   PIC X(8).\n       01  WS-X     PIC X(8)."
    p = _call("           MOVE 'SUBA' TO WS-PGM\n           CALL WS-PGM", ws, tmp_path)
    assert p["resolvedCalls"] == {"WS-PGM": "SUBA"}


def test_reading_the_identifier_is_harmless(tmp_path):
    body = ("           DISPLAY 'CALLING ' WS-PGM\n           MOVE WS-PGM TO WS-X\n"
            "           IF WS-PGM = 'SUBA' DISPLAY 'YES' END-IF\n           CALL WS-PGM")
    assert _call(body, WS_PGM, tmp_path)["resolvedCalls"] == {"WS-PGM": "SUBA"}


@pytest.mark.parametrize("statement", [
    "MOVE WS-X TO WS-PGM",
    "MOVE 'SUB' TO WS-PGM",  # a second, different literal
    "STRING 'SU' 'BA' DELIMITED BY SIZE INTO WS-PGM",
    "UNSTRING WS-X DELIMITED BY ',' INTO WS-PGM",
    "ACCEPT WS-PGM",
    "READ IN-F INTO WS-PGM",
    "INITIALIZE WS-PGM",
    "SET WS-PGM TO NULL",
    "INSPECT WS-PGM REPLACING ALL 'A' BY 'B'",
    "MOVE FUNCTION UPPER-CASE(WS-X) TO WS-PGM",
    "MOVE SPACES TO WS-PGM",
    "MOVE 'SUBA' TO WS-X MOVE WS-X TO WS-PGM",
    "CALL 'SUBA' USING WS-PGM",  # the called program may change it
    "CALL 'SUBA' USING WS-X RETURNING WS-PGM",
    "MOVE CORRESPONDING WS-X TO WS-PGM",
    "PERFORM VARYING WS-PGM FROM 1 BY 1 UNTIL WS-PGM > 3 CONTINUE END-PERFORM",
    "ADD 1 TO WS-PGM",
    "MOVE 'SUBA' TO WS-PGM(1:2)",
])
def test_any_other_way_to_assign_the_identifier_keeps_the_call_refused(tmp_path, statement):
    p = _call(f"           {statement}\n           CALL WS-PGM", WS_PGM, tmp_path)
    assert not p["convertible"] and "dynamic CALL through WS-PGM" in p["notConvertibleReason"], statement
    assert "resolvedCalls" not in p


def test_multi_line_assignments_are_seen_too(tmp_path):
    body = "           STRING 'SU'\n               'BA'\n               DELIMITED BY SIZE\n               INTO\n               WS-PGM\n           CALL WS-PGM"
    p = _call(body, WS_PGM, tmp_path)
    assert not p["convertible"] and "dynamic CALL" in p["notConvertibleReason"]


@pytest.mark.parametrize("ws, why", [
    ("       01  WS-X     PIC X(8).", "no definition in WORKING-STORAGE"),
    ("       01  WS-PGM   PIC X(8) VALUE 'SUBA'.\n       01  WS-ALIAS REDEFINES WS-PGM PIC X(8).\n"
     "       01  WS-X     PIC X(8).", "redefined"),
    ("       01  WS-PGM   PIC X(8) VALUE 'SUBA' OCCURS 2.\n       01  WS-X     PIC X(8).", "table"),
    ("       01  WS-GRP.\n           05  WS-PGM   PIC X(8) VALUE 'SUBA'.\n       01  WS-X     PIC X(8).", "inside a group"),
])
def test_definitions_that_can_change_behind_our_back_are_refused(tmp_path, ws, why):
    p = _call("           CALL WS-PGM", ws, tmp_path)
    assert not p["convertible"] and "dynamic CALL through WS-PGM" in p["notConvertibleReason"], why


def test_linkage_parameter_is_never_resolved(tmp_path):
    text = _program("           CALL LS-PGM", "       01  WS-X   PIC X.\n       LINKAGE SECTION.\n"
                    "       01  LS-PGM   PIC X(8) VALUE 'SUBA'.")
    p = _analyze(tmp_path, text, {"SUBA.cbl": SUB})
    assert not p["convertible"] and "dynamic CALL through LS-PGM" in p["notConvertibleReason"]


def test_two_literals_are_refused_even_when_both_programs_exist(tmp_path):
    ws = "       01  WS-PGM   PIC X(8) VALUE 'SUBA'.\n       01  WS-X     PIC X(8)."
    p = _call("           MOVE 'SUBB' TO WS-PGM\n           CALL WS-PGM", ws, tmp_path, {"SUBB.cbl": SUB_B})
    assert not p["convertible"] and "dynamic CALL" in p["notConvertibleReason"]


def test_resolved_target_must_still_be_in_the_repository(tmp_path):
    ws = "       01  WS-PGM   PIC X(8) VALUE 'NOWHERE'.\n       01  WS-X     PIC X(8)."
    p = _call("           CALL WS-PGM", ws, tmp_path)
    assert not p["convertible"] and "NOWHERE" in p["notConvertibleReason"]


def test_end_call_is_not_a_dynamic_call(tmp_path):
    body = "           CALL 'SUBA'\n               ON EXCEPTION DISPLAY 'FAILED'\n           END-CALL\n           DISPLAY 'AFTER'"
    info = parse_program(_program(body))
    assert info.dynamic_calls == [] and info.calls == ["SUBA"]


def test_one_resolved_and_one_unresolved_identifier(tmp_path):
    ws = ("       01  WS-PGM   PIC X(8) VALUE 'SUBA'.\n       01  WS-OTHER PIC X(8).\n       01  WS-X     PIC X(8).")
    p = _call("           ACCEPT WS-OTHER\n           CALL WS-PGM\n           CALL WS-OTHER", ws, tmp_path)
    assert not p["convertible"] and "WS-OTHER" in p["notConvertibleReason"] and "WS-PGM" not in p["notConvertibleReason"]


# --- a JCL job does not inherit the new shapes: its check compares output files only -----------------------------

@pytest.mark.parametrize("body, org", [("           OPEN INPUT IN-F\n           DISPLAY 'HI'\n           CLOSE IN-F", "LINE SEQUENTIAL"),
                                       ("           OPEN I-O IN-F\n           CLOSE IN-F", "SEQUENTIAL")])
def test_sort_then_display_only_or_io_program_is_not_a_convertible_job(tmp_path, body, org):
    (tmp_path / "MAINP.cbl").write_text(_program(body, org=org).replace("ASSIGN TO INDD", "ASSIGN TO XIN"))
    (tmp_path / "SORTTXN").write_text("  SORT FIELDS=(1,4,CH,A)\n")
    (tmp_path / "QMKX010.jcl").write_text("\n".join([
        "//QMKX010  JOB (1),'X'", "//SORT005  EXEC PGM=SORT", "//SORTIN   DD DSN=QMK.TEST.IN,DISP=SHR",
        "//SORTOUT  DD DSN=QMK.TEST.SORTED,DISP=(NEW,CATLG)", "//SYSIN    DD DSN=QMK.CNTLLIB(SORTTXN),DISP=SHR",
        "//STEP1    EXEC PGM=MAINP", "//XIN      DD DSN=QMK.TEST.SORTED,DISP=SHR"]))
    report = analyze(tmp_path)
    [job] = report["jobs"]
    [program] = report["programs"]
    assert program["convertible"]  # on its own it does convert
    assert not job["convertible"] and "compares output files only" in job["notConvertibleReason"]
