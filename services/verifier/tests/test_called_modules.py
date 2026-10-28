"""A program that CALLs another program in the repository is analyzed, linked and verified with it."""
import json
from pathlib import Path

from diocle_analyzer.analyze import analyze, write_sample
from diocle_verifier.verify import passes, verify_sample

MAIN = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. TRIPLE.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO TRIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO TROUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC.
           05  IN-AMT       PIC S9(5)V999 SIGN LEADING SEPARATE.
       FD  OUT-F.
       01  OUT-REC.
           05  OUT-AMT      PIC S9(7)V99 SIGN LEADING SEPARATE.
       WORKING-STORAGE SECTION.
       01  WS-EOF           PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT IN-F
           OPEN OUTPUT OUT-F
           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-F AT END MOVE 'Y' TO WS-EOF
               NOT AT END
                   CALL 'ROUNDIT' USING IN-AMT OUT-AMT
                   WRITE OUT-REC
               END-READ
           END-PERFORM
           CLOSE IN-F OUT-F
           STOP RUN.
"""

MODULE = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ROUNDIT.
       DATA DIVISION.
       LINKAGE SECTION.
       01  L-IN   PIC S9(5)V999 SIGN LEADING SEPARATE.
       01  L-OUT  PIC S9(7)V99 SIGN LEADING SEPARATE.
       PROCEDURE DIVISION USING L-IN L-OUT.
           COMPUTE L-OUT ROUNDED = L-IN * 3
           GOBACK.
"""

JAVA = """import java.math.*; import java.nio.file.*; import java.util.*;
public class Triple {
    public static void main(String[] a) throws Exception {
        List<String> out = new ArrayList<>();
        for (String l : Files.readAllLines(Path.of(System.getenv("DD_TRIN")))) {
            BigDecimal v = new BigDecimal(l.substring(1)).movePointLeft(3);
            if (l.charAt(0) == '-') v = v.negate();
            BigDecimal r = v.multiply(BigDecimal.valueOf(3)).setScale(2, RoundingMode.HALF_UP);
            String d = r.abs().movePointRight(2).toBigInteger().toString();
            out.add((r.signum() < 0 ? "-" : "+") + "0".repeat(9 - d.length()) + d);
        }
        Files.write(Path.of(System.getenv("DD_TROUT")), out);
    }
}
"""


def test_called_program_is_found_linked_and_verified(tmp_path):
    repo = tmp_path / "repo"
    (repo / "cobol").mkdir(parents=True)
    (repo / "cobol" / "TRIPLE.cbl").write_text(MAIN)
    (repo / "cobol" / "ROUNDIT.cbl").write_text(MODULE)
    assert all(len(l) <= 72 for l in (MAIN + MODULE).splitlines())
    report = analyze(repo)
    main = next(p for p in report["programs"] if p["name"] == "TRIPLE")
    assert main["convertible"] and main["modules"] == ["cobol/ROUNDIT.cbl"]
    sample = write_sample(repo, report, main, tmp_path / "samples")
    assert json.loads((sample / "sample.json").read_text())["modules"] == ["src/ROUNDIT.cbl"]
    (tmp_path / "java").mkdir()
    (tmp_path / "java" / "Triple.java").write_text(JAVA)
    result = verify_sample(sample, tmp_path / "java", random_count=40)
    assert passes(result), result["runs"]["original"]["stderr"][-500:]
