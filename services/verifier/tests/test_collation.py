"""With collation "ebcdic" the oracle compares in mainframe order, so a Java port using String order is caught."""
import json
from pathlib import Path

from diocle_verifier.verify import passes, verify_sample

COBOL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ORDERK.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO ORDIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO ORDOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC.
           05  IN-A         PIC X(2).
           05  IN-B         PIC X(2).
       FD  OUT-F.
       01  OUT-REC.
           05  OUT-CMP      PIC X(2).
       WORKING-STORAGE SECTION.
       01  WS-EOF           PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT IN-F
           OPEN OUTPUT OUT-F
           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-F AT END MOVE 'Y' TO WS-EOF
               NOT AT END
                   IF IN-A > IN-B
                       MOVE 'GT' TO OUT-CMP
                   ELSE
                       MOVE 'LE' TO OUT-CMP
                   END-IF
                   WRITE OUT-REC
               END-READ
           END-PERFORM
           CLOSE IN-F OUT-F
           STOP RUN.
"""

JAVA = """import java.nio.charset.Charset; import java.nio.file.*; import java.util.*;
public class Orderk {
    static int cmp(String a, String b) {
        if (!"EBCDIC".equals(System.getenv("DIOCLE_COLLATION")) || ASCII) return a.compareTo(b);
        byte[] x = a.getBytes(Charset.forName("Cp037")), y = b.getBytes(Charset.forName("Cp037"));
        for (int i = 0; i < Math.min(x.length, y.length); i++)
            if (x[i] != y[i]) return (x[i] & 0xFF) - (y[i] & 0xFF);
        return x.length - y.length;
    }
    public static void main(String[] args) throws Exception {
        List<String> out = new ArrayList<>();
        for (String l : Files.readAllLines(Path.of(System.getenv("DD_ORDIN")))) {
            l = String.format("%-4s", l);
            out.add(cmp(l.substring(0, 2), l.substring(2, 4)) > 0 ? "GT" : "LE");
        }
        Files.write(Path.of(System.getenv("DD_ORDOUT")), out);
    }
}
"""


def _sample(tmp: Path, ascii_port: bool) -> tuple[Path, Path]:
    (tmp / "src").mkdir(parents=True)
    (tmp / "copybooks").mkdir()
    (tmp / "src" / "ORDERK.cbl").write_text(COBOL)
    (tmp / "java").mkdir()
    (tmp / "java" / "Orderk.java").write_text(JAVA.replace("ASCII", str(ascii_port).lower()))
    x2 = {"kind": "alnum", "length": 2}
    (tmp / "sample.json").write_text(json.dumps({
        "program": "ORDERK", "source": "src/ORDERK.cbl", "copybookDir": "copybooks", "collation": "ebcdic",
        "dd": {"input": "ORDIN", "output": "ORDOUT"}, "javaConversion": {"dir": "java", "mainClass": "Orderk"},
        "layouts": {"input": {"record": "IN-REC", "fields": [{"name": "IN-A", **x2}, {"name": "IN-B", **x2}]},
                    "output": {"record": "OUT-REC", "fields": [{"name": "OUT-CMP", **x2}]}},
        "fixtureCases": [{"id": "lower-vs-upper", "record": "aaAA"}, {"id": "digit-vs-letter", "record": "11AA"},
                         {"id": "mixed", "record": "A1AB"}]}))
    return tmp, tmp / "java"


def test_ebcdic_ordering_is_the_oracle(tmp_path):
    assert all(len(l) <= 72 for l in COBOL.splitlines())
    good = verify_sample(*_sample(tmp_path / "ebcdic", ascii_port=False), random_count=10)
    assert passes(good) and good["runs"]["collation"] == "ebcdic"
    bad = verify_sample(*_sample(tmp_path / "ascii", ascii_port=True), random_count=10)
    assert {r["inputId"] for r in bad["results"] if not r["match"]} == {
        "fixture-lower-vs-upper", "fixture-digit-vs-letter", "fixture-mixed"}
