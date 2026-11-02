"""A free-format program whose copybooks have no directive of their own and start in columns 1-7, from the analyzer to a
certificate: cobc -free reads the members as free-format, and the analyzer has to agree. Hand-written Java fixture."""
import shutil

import pytest

from diocle_analyzer.analyze import analyze, write_sample
from diocle_verifier.verify import passes, verify_sample

PROGRAM = """>>SOURCE FORMAT FREE
IDENTIFICATION DIVISION.
PROGRAM-ID. FREEPGM.
ENVIRONMENT DIVISION.
INPUT-OUTPUT SECTION.
FILE-CONTROL.
    SELECT IN-FILE ASSIGN TO INFILE ORGANIZATION IS SEQUENTIAL.
    SELECT OUT-FILE ASSIGN TO OUTFILE ORGANIZATION IS SEQUENTIAL.
DATA DIVISION.
FILE SECTION.
FD IN-FILE.
COPY FREEIN.
FD OUT-FILE.
COPY FREEOUT.
WORKING-STORAGE SECTION.
COPY FREEWS.
PROCEDURE DIVISION.
    OPEN INPUT IN-FILE OUTPUT OUT-FILE.
    PERFORM UNTIL WS-EOF = 'Y'
        READ IN-FILE AT END MOVE 'Y' TO WS-EOF
        NOT AT END
            MOVE IN-ID TO OUT-ID
            MOVE IN-AMT TO OUT-AMT
            WRITE OUT-REC
        END-READ
    END-PERFORM.
    CLOSE IN-FILE OUT-FILE.
    STOP RUN.
"""
JAVA = """import java.nio.file.*;
public class Freepgm { public static void main(String[] a) throws Exception {
  Files.write(Path.of(System.getenv("DD_OUTFILE")), Files.readAllBytes(Path.of(System.getenv("DD_INFILE")))); } }
"""


@pytest.mark.skipif(not (shutil.which("cobc") and shutil.which("javac")), reason="needs GnuCOBOL and a JDK")
def test_free_format_program_with_column_1_copybooks_is_certified_end_to_end(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "FREEPGM.cbl").write_text(PROGRAM)
    (repo / "FREEIN.cpy").write_text("01 IN-REC.\n   05 IN-ID PIC X(5).\n   05 IN-AMT PIC 9(5).\n")
    (repo / "FREEOUT.cpy").write_text("01 OUT-REC.\n   05 OUT-ID PIC X(5).\n   05 OUT-AMT PIC 9(5).\n")
    (repo / "FREEWS.cpy").write_text("COPY FREENEST.\n")
    (repo / "FREENEST.cpy").write_text("01 WS-EOF PIC X VALUE 'N'.\n")
    report = analyze(repo)
    program = next(p for p in report["programs"] if p["name"] == "FREEPGM")
    assert program["convertible"], program["notConvertibleReason"]
    sample = write_sample(repo, report, program, tmp_path / "out")  # carries FREENEST, or the original would not compile
    java = tmp_path / "java"
    java.mkdir()
    (java / "Freepgm.java").write_text(JAVA)
    result = verify_sample(sample, java, seed=5, random_count=30)
    assert result["runs"]["original"]["compiled"] and result["summary"]["total"] > 0
    assert passes(result), [r for r in result["results"] if not r["match"]][:2]
