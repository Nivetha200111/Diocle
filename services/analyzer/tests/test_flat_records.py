"""Flat line-sequential records (01 IN-RECORD PIC X(n), sliced by reference modification), their seed records from
the repository's own data files, and CALL inside a string literal.

A flat record has one alphanumeric field, so generated inputs are filler a real program rejects on its first byte;
the repository's data files are what make the differential test reach the program's real paths."""
import json
from pathlib import Path

from diocle_analyzer.analyze import REPO_FIXTURE_MAX, analyze, repo_fixtures, validate_report, write_sample
from diocle_analyzer.cobol import parse_program

FLAT = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. FLATP.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO INPUT-FILE
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-FILE ASSIGN TO OUTPUT-FILE
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-FILE.
       01  IN-RECORD PIC X(20).
       FD  OUT-FILE.
       01  OUT-RECORD PIC X(30).
       WORKING-STORAGE SECTION.
       01  WS-EOF PIC X VALUE "N".
       PROCEDURE DIVISION.
           OPEN INPUT IN-FILE OUTPUT OUT-FILE
           PERFORM UNTIL WS-EOF = "Y"
               READ IN-FILE AT END MOVE "Y" TO WS-EOF
               NOT AT END
                   MOVE IN-RECORD(1:12) TO OUT-RECORD
                   WRITE OUT-RECORD
               END-READ
           END-PERFORM
           CLOSE IN-FILE OUT-FILE
           STOP RUN.
"""


def _flat(tmp_path: Path, data: dict[str, str] | None = None) -> tuple[dict, dict]:
    (tmp_path / "FLATP.cbl").write_text(FLAT)
    for name, text in (data or {}).items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    report = analyze(tmp_path)
    validate_report(report)
    return report, next(p for p in report["programs"] if p["name"] == "FLATP")


def test_an_elementary_record_is_one_field_and_convertible(tmp_path):
    _, p = _flat(tmp_path)
    assert p["convertible"], p["notConvertibleReason"]
    layout = next(f for f in p["files"] if f["direction"] == "input")["layout"]
    assert layout["fields"] == [{"name": "IN-RECORD", "kind": "alnum", "length": 20}]


def test_data_files_that_fit_the_record_seed_it_with_their_origin(tmp_path):
    rows = "".join(f"A{i:010d}BR{i:07d}\n" for i in range(1, 51))  # 20 characters each
    report, p = _flat(tmp_path, {"data/accounts.dat": rows, "data/short.dat": "T1\nT" + "2" * 19 + "\n"})
    meta = json.loads((write_sample(tmp_path, report, p, tmp_path / "out") / "sample.json").read_text())
    cases = meta["fixtureCases"]
    assert {c["why"].split(" of ")[1].split(" in ")[0] for c in cases} == {"data/accounts.dat", "data/short.dat"}
    assert all(len(c["record"]) == 20 for c in cases)
    assert cases[0] == {"id": "repo-0001", "record": "A0000000001BR0000001",
                        "why": "line 1 of data/accounts.dat in the imported repository"}
    assert "T1" + " " * 18 in [c["record"] for c in cases]  # a trimmed line-sequential record is padded back


def test_files_that_do_not_fit_or_are_not_data_are_ignored(tmp_path):
    wide = "X" * 21 + "\n"
    narrow = "X" * 19 + "\n"  # nothing reaches the record length: not this file's data
    expected = "Y" * 20 + "\n"
    _, p = _flat(tmp_path, {"wide.dat": wide, "narrow.dat": narrow, "app/expected/flatp.out": expected,
                            "README.md": "Z" * 20 + "\n", "bin.dat": ""})
    layout = next(f for f in p["files"] if f["direction"] == "input")["layout"]
    assert repo_fixtures(tmp_path, layout) == []


def test_seeds_are_capped_and_spread_over_each_file(tmp_path):
    rows = "".join(f"{i:020d}\n" for i in range(1, 2001))
    _, p = _flat(tmp_path, {"a.dat": rows, "b.dat": rows})
    layout = next(f for f in p["files"] if f["direction"] == "input")["layout"]
    cases = repo_fixtures(tmp_path, layout)
    assert len(cases) == REPO_FIXTURE_MAX
    from_a = [int(c["record"]) for c in cases if " a.dat " in c["why"]]
    assert len(from_a) == REPO_FIXTURE_MAX // 2 and from_a[0] == 1 and from_a[-1] > 1900  # the whole file, not its head


def test_structured_layouts_keep_generated_inputs_only(tmp_path):
    layout = {"record": "R", "format": "line", "fields": [{"name": "A", "kind": "alnum", "length": 10},
                                                          {"name": "B", "kind": "alnum", "length": 10}]}
    (tmp_path / "x.dat").write_text("Q" * 20 + "\n")
    assert repo_fixtures(tmp_path, layout) == []


def test_call_inside_a_string_literal_is_not_a_call():
    text = FLAT.replace('MOVE "Y" TO WS-EOF', 'MOVE "CALL FAILED" TO WS-EOF')
    info = parse_program(text)
    assert info.dynamic_calls == [] and info.calls == []


def test_free_format_lines_are_read_whole():
    from diocle_analyzer.cobol import source_lines
    text = (">>SOURCE FORMAT FREE\n       IDENTIFICATION DIVISION.\n*> a comment line\n"
            "       PROGRAM-ID. FREEP. *> trailing comment\n"
            + "           IF A > B MOVE 'R01' TO C ELSE MOVE '   ' TO C END-IF" + " " * 0 + "\n")
    lines = dict(source_lines(text))
    assert 1 not in lines and 3 not in lines
    assert lines[4].strip() == "PROGRAM-ID. FREEP."
    assert lines[5].rstrip().endswith("END-IF")  # past column 72: fixed format would cut it off
