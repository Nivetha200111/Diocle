"""The verifier pins the clock for both sides and compares exit codes (COBOL RETURN-CODE)."""
import json
from pathlib import Path

from diocle_verifier.verify import passes, verify_sample

COBOL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. STAMP.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO STAMPIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO STAMPOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC.
           05  IN-ID        PIC X(4).
       FD  OUT-F.
       01  OUT-REC.
           05  OUT-ID       PIC X(4).
           05  OUT-DATE     PIC 9(8).
       WORKING-STORAGE SECTION.
       01  WS-EOF           PIC X VALUE 'N'.
       01  WS-DATE          PIC 9(8).
       PROCEDURE DIVISION.
           ACCEPT WS-DATE FROM DATE YYYYMMDD
           OPEN INPUT IN-F OUTPUT OUT-F
           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-F AT END MOVE 'Y' TO WS-EOF
               NOT AT END
                   MOVE IN-ID TO OUT-ID
                   MOVE WS-DATE TO OUT-DATE
                   WRITE OUT-REC
               END-READ
           END-PERFORM
           CLOSE IN-F OUT-F
           MOVE 4 TO RETURN-CODE
           STOP RUN.
"""

JAVA = """import java.nio.file.*; import java.util.*;
public class Stamp {
    public static void main(String[] a) throws Exception {
        String clock = System.getenv("DIOCLE_CLOCK");
        String date = clock.substring(0, 10).replace("-", "");
        List<String> out = new ArrayList<>();
        for (String l : Files.readAllLines(Path.of(System.getenv("DD_STAMPIN"))))
            out.add(String.format("%-4s", l).substring(0, 4) + date);
        Files.write(Path.of(System.getenv("DD_STAMPOUT")), out);
        System.exit(EXIT);
    }
}
"""


def test_the_test_program_fits_in_72_columns():
    assert all(len(line) <= 72 for line in COBOL.splitlines())


def _sample(tmp: Path, exit_code: int) -> tuple[Path, Path]:
    (tmp / "src").mkdir()
    (tmp / "copybooks").mkdir()
    (tmp / "src" / "STAMP.cbl").write_text(COBOL)
    (tmp / "java").mkdir()
    (tmp / "java" / "Stamp.java").write_text(JAVA.replace("EXIT", str(exit_code)))
    (tmp / "sample.json").write_text(json.dumps({
        "program": "STAMP", "source": "src/STAMP.cbl", "copybookDir": "copybooks",
        "dd": {"input": "STAMPIN", "output": "STAMPOUT"},
        "javaConversion": {"dir": "java", "mainClass": "Stamp"},
        "layouts": {"input": {"record": "IN-REC", "fields": [{"name": "IN-ID", "kind": "alnum", "length": 4}]},
                    "output": {"record": "OUT-REC", "fields": [{"name": "OUT-ID", "kind": "alnum", "length": 4},
                               {"name": "OUT-DATE", "kind": "numeric", "digits": 8, "scale": 0, "signed": False}]}}}))
    return tmp, tmp / "java"


def test_same_clock_and_same_return_code_pass(tmp_path):
    report = verify_sample(*_sample(tmp_path, 4), random_count=5)
    assert report["runs"]["original"]["exitCode"] == 4 and report["runs"]["exitCodeMatch"]
    assert report["runs"]["clock"].startswith("2000-02-29")
    assert report["results"][0]["originalOutput"].endswith("20000229")  # GnuCOBOL saw the pinned date
    assert passes(report)


def test_a_different_return_code_fails_even_when_records_match(tmp_path):
    report = verify_sample(*_sample(tmp_path, 0), random_count=5)
    assert report["summary"]["failed"] == 0 and not report["runs"]["exitCodeMatch"] and not passes(report)
