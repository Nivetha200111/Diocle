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


# --- review fixes: literals and comments one line at a time ------------------------------------------------

CALLER = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALLR.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-PGM PIC X(8).
       01  WS-MSG PIC X(80) VALUE 'THIS LONG MESSAGE CONTINUES ON
      -    'TO THE NEXT LINE'.
       PROCEDURE DIVISION.
           MOVE "X" TO WS-PGM *> don't remove
           ACCEPT WS-PGM
           CALL WS-PGM
           STOP RUN.
"""


def test_an_unbalanced_quote_never_hides_a_later_dynamic_call():
    assert parse_program(CALLER).dynamic_calls == ["WS-PGM"]
    free = ">>SOURCE FORMAT FREE\n" + CALLER.replace("      -    'TO THE NEXT LINE'.", "      'TO THE NEXT LINE'.")
    assert parse_program(free).dynamic_calls == ["WS-PGM"]


def test_free_format_comment_is_cut_after_a_closed_literal_but_not_inside_one():
    from diocle_analyzer.cobol import source_lines
    lines = dict(source_lines('>>SOURCE FORMAT FREE\n       DISPLAY "X" *> CALL WS-PGM\n       DISPLAY "A *> B".\n'))
    assert lines[2].strip() == 'DISPLAY "X"' and lines[3].strip() == 'DISPLAY "A *> B".'


def test_free_format_code_past_column_72_is_not_reported_as_cut(tmp_path):
    from diocle_analyzer.risks import _source_findings
    long = "           DISPLAY '" + "ABCDEFGHIJ" * 7 + "'"  # text across columns 72-73
    assert len(long) > 72
    assert _source_findings("P", ">>SOURCE FORMAT FREE\n" + long + "\n") == []
    assert _source_findings("P", long + "\n")  # fixed format: still flagged


# --- review fixes: which files are data ---------------------------------------------------------------------

def test_the_file_the_jcl_dataset_names_is_preferred(tmp_path):
    from diocle_analyzer.analyze import _names_dataset
    assert _names_dataset("HT.SYNTH.LOANIN", "app/data/loans.dat") and _names_dataset("HT.SYNTH.ACCTIN", "accounts.dat")
    assert _names_dataset("HT.SYNTH.FXIN", "fx-rates.dat") and not _names_dataset("HT.SYNTH.LOANIN", "accounts.dat")
    assert not _names_dataset(None, "loans.dat") and not _names_dataset("&&SORTED", "sorted.dat")
    _, p = _flat(tmp_path, {"data/loans.dat": "L" * 20 + "\n", "data/accounts.dat": "A" * 20 + "\n"})
    layout = next(f for f in p["files"] if f["direction"] == "input")["layout"]
    assert {c["record"][0] for c in repo_fixtures(tmp_path, layout, "HT.SYNTH.LOANIN")} == {"L"}
    assert {c["record"][0] for c in repo_fixtures(tmp_path, layout, "HT.SYNTH.POSTIN")} == {"L", "A"}  # no match: all


def test_sources_docs_and_non_ascii_files_are_never_data(tmp_path):
    member = "".join(f"{i:06d} MOVE A TO B.  \n"[:20].ljust(20) + "\n" for i in range(3))  # 20-wide, looks like data
    cobol_member = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. OTHER.\n"
    copybook = "       01  R.\n           05 A PIC X(9).\n"
    _, p = _flat(tmp_path, {"QMK.COBOL/OTHER": cobol_member, "QMK.COPY/RECA": copybook.ljust(20),
                            "LICENSE": "Y" * 20 + "\n", "notes/euro.dat": "PRICE €" + "Z" * 13 + "\n",
                            "seq/members.dat": member, ".hidden/x.dat": "H" * 20 + "\n"})
    layout = next(f for f in p["files"] if f["direction"] == "input")["layout"]
    used = {c["why"].split(" of ")[1].split(" in ")[0] for c in repo_fixtures(tmp_path, layout)}
    assert used == {"seq/members.dat"}


def test_nested_copybooks_travel_with_the_program(tmp_path):
    out_dir, tmp_path = tmp_path / "out", tmp_path / "repo"
    tmp_path.mkdir()
    text = FLAT.replace("       WORKING-STORAGE SECTION.\n", "       WORKING-STORAGE SECTION.\n       COPY NESTA.\n")
    (tmp_path / "FLATP.cbl").write_text(text)
    (tmp_path / "NESTA.cpy").write_text("       COPY NESTB.\n")
    (tmp_path / "NESTB.cpy").write_text("       01  WS-B PIC X.\n       01  WS-M PIC X(20) VALUE 'RECORD COPY FAILED'.\n")
    report = analyze(tmp_path)
    p = next(p for p in report["programs"] if p["name"] == "FLATP")
    assert p["copybooks"] == ["NESTA", "NESTB"] and p["convertible"]
    sample = write_sample(tmp_path, report, p, out_dir)
    assert sorted(f.name for f in (sample / "copybooks").iterdir()) == ["NESTA.cpy", "NESTB.cpy"]
    (tmp_path / "NESTB.cpy").unlink()
    p = next(p for p in analyze(tmp_path)["programs"] if p["name"] == "FLATP")
    assert not p["convertible"] and "NESTB" in p["notConvertibleReason"]


# --- a free-format program's format applies to the copybooks it pulls in (cobc -free reads them all as free) ---------

FREE_PROGRAM = """>>SOURCE FORMAT FREE
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
01 OUT-REC PIC X(10).
WORKING-STORAGE SECTION.
COPY FREEWS.
PROCEDURE DIVISION.
    OPEN INPUT IN-FILE OUTPUT OUT-FILE.
    CLOSE IN-FILE OUT-FILE.
    STOP RUN.
"""
FREE_IN = "01 IN-REC.\n   05 IN-ID PIC X(5).\n   05 IN-AMT PIC 9(5).\n"


def _free_repo(tmp_path, source=FREE_PROGRAM, members=None):
    (tmp_path / "FREEPGM.cbl").write_text(source)
    for name, text in {"FREEIN": FREE_IN, "FREEWS": "COPY FREENEST.\n", "FREENEST": "01 WS-EOF PIC X.\n", **(members or {})}.items():
        if text is not None:
            (tmp_path / f"{name}.cpy").write_text(text)
    return next(p for p in analyze(tmp_path)["programs"] if p["name"] == "FREEPGM")


def test_a_free_programs_copybooks_are_read_as_free_format(tmp_path):
    p = _free_repo(tmp_path)
    assert p["convertible"], p["notConvertibleReason"]
    assert [f["name"] for f in p["files"][0]["layout"]["fields"]] == ["IN-ID", "IN-AMT"]
    assert p["copybooks"] == ["FREEIN", "FREEWS", "FREENEST"]  # the nested COPY in columns 1-7 is found


def test_a_missing_nested_member_of_a_free_program_is_refused_before_any_translation(tmp_path):
    p = _free_repo(tmp_path, members={"FREENEST": None})
    assert not p["convertible"] and "FREENEST" in p["notConvertibleReason"]


def test_a_member_that_declares_fixed_stays_fixed_in_a_free_program(tmp_path):
    fixed = (">>SOURCE FORMAT FIXED\n000100 01  IN-REC.\n000200     05  IN-ID PIC X(5).\n      * a comment\n"
             "000300     05  IN-AMT PIC 9(5).\n")
    p = _free_repo(tmp_path, members={"FREEIN": fixed})
    assert p["convertible"], p["notConvertibleReason"]
    assert [f["name"] for f in p["files"][0]["layout"]["fields"]] == ["IN-ID", "IN-AMT"]


def test_a_fixed_program_still_reads_its_copybooks_as_fixed(tmp_path):
    fixed = FREE_PROGRAM.removeprefix(">>SOURCE FORMAT FREE\n")
    fixed = "".join("       " + line + "\n" for line in fixed.splitlines())
    p = _free_repo(tmp_path, fixed)
    assert not p["convertible"] and "no 01 level" in p["notConvertibleReason"]  # cobc reads FREEIN by columns too


def test_each_module_reads_its_copybooks_in_its_own_format(tmp_path):
    (tmp_path / "MAINP.cbl").write_text("""       IDENTIFICATION DIVISION.
       PROGRAM-ID. MAINP.
       PROCEDURE DIVISION.
           CALL 'FREESUB'
           DISPLAY 'DONE'
           STOP RUN.
""")
    (tmp_path / "FREESUB.cbl").write_text(""">>SOURCE FORMAT FREE
IDENTIFICATION DIVISION.
PROGRAM-ID. FREESUB.
DATA DIVISION.
WORKING-STORAGE SECTION.
COPY SUBWS.
PROCEDURE DIVISION.
    GOBACK.
""")
    (tmp_path / "SUBWS.cpy").write_text("COPY SUBNEST.\n")
    (tmp_path / "SUBNEST.cpy").write_text("01 WS-A PIC X.\n")
    p = next(p for p in analyze(tmp_path)["programs"] if p["name"] == "MAINP")
    assert p["copybooks"] == ["SUBWS", "SUBNEST"]


def test_interface_checks_read_a_free_programs_copybooks_as_free_format():
    from diocle_analyzer.interfaces import Source, _sizes, copybook_drift
    program = ">>SOURCE FORMAT FREE\nPROGRAM-ID. P{n}.\nFILE SECTION.\nFD F.\nCOPY REC.\nWORKING-STORAGE SECTION.\nCOPY WS.\n"
    wide = "01 R.\n   05 A PIC X(9).\n"
    assert _sizes(program.format(n=1), {"WS": ("WS.cpy", "01 WS-A PIC X(7).\n")})["WS-A"] == 7
    _, drift = copybook_drift([Source("P1", "p1.cbl", program.format(n=1), {"REC": ("c/REC.cpy", wide)}),
                               Source("P2", "p2.cbl", program.format(n=2), {"REC": ("d/REC.cpy", wide.replace("9", "4"))})])
    assert drift  # read by columns, both members were empty and looked the same
