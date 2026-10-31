"""COPY is recognised only as a statement, never as the tail of a data name such as REQUEST-MSG-COPY.

The program here is SYNTHETIC, written for this test."""
from pathlib import Path

from diocle_analyzer.analyze import analyze, validate_report
from diocle_analyzer.cobol import parse_program

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


def _repo(tmp_path: Path, abend: str = "", extra: dict[str, str] | None = None) -> Path:
    (tmp_path / "PFXREC.cpy").write_text("       01  :P:-REC.\n           05  :P:-ID   PIC X(4).\n")
    (tmp_path / "WSCOUNT.cpy").write_text("       01  WS-COUNT     PIC 9(4) VALUE 0.\n")
    (tmp_path / "MSGCOPY.cbl").write_text(PROGRAM.format(abend=abend))
    for name, text in (extra or {}).items():
        (tmp_path / name).write_text(text)
    return tmp_path


def _program(report: dict, name: str = "MSGCOPY") -> dict:
    return next(p for p in report["programs"] if p["name"] == name)


def test_copy_inside_a_data_name_is_not_a_copy_statement(tmp_path):
    info = parse_program(PROGRAM.format(abend=""))
    assert info.copybooks == ["PFXREC", "WSCOUNT"]  # not REPLACING (from X-COPY REPLACING) nor PERFORM
    assert info.fd_copybooks["IN-F"] == "PFXREC" and info.replacing["IN-F"] == [("==:P:==", "==MSG==")]
    report = analyze(_repo(tmp_path))
    validate_report(report)
    p = _program(report)
    assert p["copybooks"] == ["PFXREC", "WSCOUNT"]
    copies = {d["to"] for d in report["dependencies"] if d["kind"] == "copy"}
    assert copies == {"PFXREC", "WSCOUNT"}
    assert p["convertible"], p["notConvertibleReason"]
    assert p["files"][0]["layout"]["fields"][0]["name"] == "MSG-ID"  # COPY REPLACING still applied


def test_copy_at_the_end_of_an_underscore_name_is_not_a_copy_statement():
    code = "\n".join([
        "       IDENTIFICATION DIVISION.",
        "       PROGRAM-ID. USCOPY.",
        "       DATA DIVISION.",
        "       WORKING-STORAGE SECTION.",
        "       COPY WSCOUNT.",
        "       01  MY_COPY      PIC X.",
        "       PROCEDURE DIVISION.",
        "           MOVE 'A' TO MY_COPY",
        "           PERFORM X.",
        "       X.",
        "           STOP RUN.",
    ])
    assert parse_program(code).copybooks == ["WSCOUNT"]  # not PERFORM (from MY_COPY PERFORM)
