"""CEE3ABD (IBM LE abnormal termination) is a stated stand-in routine, not a program missing from the repository.

All programs here are SYNTHETIC, written for these tests (the program is the one in test_copy_statement.py)."""
import json
from pathlib import Path

from diocle_analyzer.analyze import analyze, validate_report, write_sample

PROGRAM = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. MSGCOPY.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO MSGIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO MSGOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       COPY PFXREC REPLACING ==:P:== BY ==MSG==.
       FD  OUT-F.
       01  OUT-REC.
           05  OUT-ID   PIC X(4).
       WORKING-STORAGE SECTION.
       COPY WSCOUNT.
       01  REQUEST-MSG-COPY.
           05  RMC-NUM  PIC 9(4).
           05  RMC-TXT  PIC X(4).
       01  ABCODE       PIC S9(9) BINARY.
       01  TIMING       PIC S9(9) BINARY.
       PROCEDURE DIVISION.
           OPEN INPUT IN-F OUTPUT OUT-F
           INITIALIZE REQUEST-MSG-COPY  REPLACING NUMERIC BY ZEROES
           INITIALIZE REQUEST-MSG-COPY
           PERFORM 1000-COPY-IT
           CLOSE IN-F OUT-F
           STOP RUN.
       1000-COPY-IT.
           MOVE MSG-ID TO OUT-ID
           WRITE OUT-REC.
{abend}"""

ABEND = """       9999-ABEND.
           DISPLAY 'ABENDING PROGRAM'
           MOVE 0 TO TIMING
           MOVE 999 TO ABCODE
           CALL 'CEE3ABD' USING ABCODE, TIMING.
"""


def _repo(tmp_path: Path, abend: str = "", extra: dict[str, str] | None = None) -> Path:
    (tmp_path / "PFXREC.cpy").write_text("       01  :P:-REC.\n           05  :P:-ID   PIC X(4).\n")
    (tmp_path / "WSCOUNT.cpy").write_text("       01  WS-COUNT     PIC 9(4) VALUE 0.\n")
    (tmp_path / "MSGCOPY.cbl").write_text(PROGRAM.format(abend=abend))
    for name, text in (extra or {}).items():
        (tmp_path / name).write_text(text)
    return tmp_path


def _program(report: dict, name: str = "MSGCOPY") -> dict:
    return next(p for p in report["programs"] if p["name"] == name)


def test_cee3abd_is_a_stated_stand_in_not_a_missing_program(tmp_path):
    report = analyze(_repo(tmp_path, ABEND))
    validate_report(report)
    p = _program(report)
    assert p["convertible"], p["notConvertibleReason"]
    assert p["standIns"] == ["CEE3ABD"] and p["modules"] == []
    assert {"from": "MSGCOPY", "to": "CEE3ABD", "kind": "call"} in report["dependencies"]
    sample = write_sample(tmp_path, report, p, tmp_path / "out")
    assert json.loads((sample / "sample.json").read_text())["standIns"] == ["CEE3ABD"]


def test_other_missing_programs_are_still_refused(tmp_path):
    abend = ABEND + "           CALL 'COBDATFT' USING ABCODE.\n"
    p = _program(analyze(_repo(tmp_path, abend)))
    assert not p["convertible"]
    assert p["notConvertibleReason"] == "CALLs program(s) not in the repository: COBDATFT"


def test_a_repository_that_defines_cee3abd_uses_its_own(tmp_path):
    own = ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. CEE3ABD.\n       PROCEDURE DIVISION.\n"
           "           GOBACK.\n")
    report = analyze(_repo(tmp_path, ABEND, {"CEE3ABD.cbl": own}))
    p = _program(report)
    assert p["convertible"] and p["modules"] == ["CEE3ABD.cbl"] and "standIns" not in p


def test_a_called_module_that_abends_puts_the_stand_in_on_the_caller(tmp_path):
    module = ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. ABENDIT.\n       DATA DIVISION.\n"
              "       WORKING-STORAGE SECTION.\n       01  ABCODE PIC S9(9) BINARY VALUE 4.\n"
              "       PROCEDURE DIVISION.\n           CALL 'CEE3ABD' USING ABCODE ABCODE\n           GOBACK.\n")
    report = analyze(_repo(tmp_path, "           CALL 'ABENDIT'.\n", {"ABENDIT.cbl": module}))
    p = _program(report)
    assert p["convertible"] and p["modules"] == ["ABENDIT.cbl"] and p["standIns"] == ["CEE3ABD"]
