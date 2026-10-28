import json
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, validate_report, write_sample
from diocle_analyzer.cobol import parse_copybook
from diocle_analyzer.github import parse_url

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
HAND_WRITTEN = ["interest-accrual", "txn-posting", "fee-schedule", "daily-control"]


@pytest.mark.parametrize("sample", HAND_WRITTEN)
def test_derived_layouts_match_hand_written_ones(sample):
    report = analyze(SAMPLES / sample)
    validate_report(report)
    meta = json.loads((SAMPLES / sample / "sample.json").read_text())
    [program] = report["programs"]
    assert program["convertible"], program["notConvertibleReason"]
    files = {f["direction"]: f for f in program["files"]}
    assert {d: files[d]["dd"] for d in ("input", "output")} == meta["dd"]
    for direction in ("input", "output"):
        derived, expected = files[direction]["layout"], meta["layouts"][direction]
        assert derived["record"] == expected["record"]
        for got, want in zip(derived["fields"], expected["fields"], strict=True):
            # The copybook only names 88-level values; the hand-written layout may list more (INTACCR's 'S' tier).
            assert {k: v for k, v in got.items() if k != "values"} == {k: v for k, v in want.items() if k != "values"}
            assert set(got.get("values", [])) <= set(want.get("values", []))


def test_findings_name_the_paragraphs_with_legacy_arithmetic():
    findings = analyze(SAMPLES / "interest-accrual")["findings"]
    seen = {(f["paragraph"], f["category"]) for f in findings}
    assert ("3000-CALC-INTEREST", "rounding") in seen
    assert ("4000-CALC-FEE", "truncation") in seen
    assert ("4000-CALC-FEE", "overflow") in seen
    assert ("9000-TERM", "display") in seen


def test_storage_formats_are_modelled():
    def fields(body):
        layout = parse_copybook("       01  R.\n" + "".join(f"           {l}\n" for l in body))
        assert layout.unsupported is None, layout.unsupported
        return layout.fields

    assert fields(["05  A  PIC S9(5)V99 COMP-3."]) == [
        {"name": "A", "kind": "numeric", "digits": 5, "scale": 2, "signed": True, "usage": "packed"}]
    assert fields(["05  A  PIC S9(4) COMP-5."])[0]["usage"] == "binary-native"
    assert fields(["05  A  PIC 9(4) BINARY."])[0]["usage"] == "binary"
    assert fields(["05  A  COMP-2."])[0] | {} == {"name": "A", "kind": "numeric", "digits": 7, "scale": 2,
                                                   "signed": True, "usage": "float", "bytes": 8}
    assert fields(["05  A  PIC S9(5)V99."])[0]["sign"] == "trailing"  # overpunch, the mainframe default
    assert fields(["05  A  PIC S9(3) SIGN LEADING."])[0]["sign"] == "leading"
    assert fields(["05  A  PIC S9(3) SIGN TRAILING SEPARATE."])[0]["sign"] == "trailing-separate"
    assert fields(["05  A  PIC 9(3)PP."])[0] | {} == {"name": "A", "kind": "numeric", "digits": 5, "scale": -2, "signed": False}
    assert fields(["05  A  PIC Z(4)9.99-."]) == [{"name": "A", "kind": "alnum", "length": 9, "edited": "ZZZZ9.99-"}]
    grouped = fields(["05  G  COMP-3.", "    10  A  PIC S9(3).", "    10  B  PIC 9(5)V9."])
    assert [f["usage"] for f in grouped] == ["packed", "packed"]  # USAGE on the group applies to its children
    table = fields(["05  T  OCCURS 2 TIMES.", "    10  K  PIC X(2).", "    10  V  PIC 9(3) COMP."])
    assert [f["name"] for f in table] == ["K(1)", "V(1)", "K(2)", "V(2)"]
    view = fields(["05  RAW  PIC X(4).", "05  NUM  REDEFINES RAW PIC 9(4)."])
    assert view[1]["redefines"] == "RAW" and view[1]["name"] == "NUM"


def test_what_cannot_be_modelled_safely_is_rejected():
    for body, reason in [(["05  N  PIC 9.", "05  A  OCCURS 1 TO 5 DEPENDING ON N PIC X."], "DEPENDING"),
                         (["05  A  PIC N(4)."], "national"),
                         (["05  A  PIC SVPP99."], "leading P")]:
        layout = parse_copybook("       01  R.\n" + "".join(f"           {l}\n" for l in body))
        assert layout.as_dict() is None and reason in layout.unsupported, (body, layout.unsupported)


def test_write_sample_produces_converter_input(tmp_path):
    report = analyze(SAMPLES / "fee-schedule")
    sample = write_sample(SAMPLES / "fee-schedule", report, report["programs"][0], tmp_path)
    meta = json.loads((sample / "sample.json").read_text())
    assert meta["javaConversion"]["mainClass"] == "Feeschd" and (sample / meta["source"]).exists()
    assert sorted(p.name for p in (sample / "copybooks").iterdir()) == ["CHGREC.cpy", "FEEREC.cpy"]


def test_only_allowed_github_owners(monkeypatch):
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    assert parse_url("https://github.com/Nivetha200111/quillmark-legacy") == ("Nivetha200111", "quillmark-legacy")
    with pytest.raises(PermissionError):
        parse_url("https://github.com/someone-else/repo")
    for bad in ("http://github.com/a/b", "https://github.com/a/b/../../c", "git@github.com:a/b.git"):
        with pytest.raises((ValueError, PermissionError)):
            parse_url(bad)


def test_visitor_imports_allow_any_owner_but_still_check_the_url(monkeypatch):
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    monkeypatch.setenv("DIOCLE_IMPORT_ANY", "1")
    assert parse_url("https://github.com/someone-else/repo") == ("someone-else", "repo")
    with pytest.raises(ValueError):
        parse_url("https://github.com/a/b/../../c")


def test_environment_and_source_findings(tmp_path):
    program = "\n".join([
        "       IDENTIFICATION DIVISION.",
        "       PROGRAM-ID. ENVT.",
        "       DATA DIVISION.",
        "       WORKING-STORAGE SECTION.",
        "       01  WS-NAME   PIC X(10).",
        "       01  WS-RATE   COMP-2.",
        "       01  WS-D      PIC 9(8).",
        "       PROCEDURE DIVISION.",
        "           ACCEPT WS-D FROM DATE YYYYMMDD",
        "           IF WS-NAME > 'M'",
        "               DISPLAY 'LATE'",
        "           END-IF",
        "           COMPUTE WS-D = WS-D * 2 +".ljust(70) + "36" + "5",  # the FEESCHD bug: '/ 365' read as '/ 36'
        "      * a comment line that is very long and runs past column seventy two on purpose x",
        "           STOP RUN.                                                    00000100",
        "           MOVE WS-D TO WS-D".ljust(64) + "WS-DATES" + "00000110",  # code to col 72, then a sequence number
    ])
    (tmp_path / "ENVT.cbl").write_text(program)
    cats = {(f["category"], f["line"]) for f in analyze(tmp_path)["findings"]}
    assert ("clock", 9) in cats and ("collation", 10) in cats and ("float", 6) in cats
    assert ("source", 13) in cats  # token cut at column 72
    assert not any(c == "source" and line in (14, 15, 16) for c, line in cats)  # comments and sequence numbers are fine


def test_copy_replacing_inline_records_and_blocking_reasons(tmp_path):
    (tmp_path / "PFXREC.cpy").write_text("       01  :P:-REC.\n           05  :P:-ID   PIC X(4).\n")
    program = "\n".join([
        "       IDENTIFICATION DIVISION.",
        "       PROGRAM-ID. RPL.",
        "       ENVIRONMENT DIVISION.",
        "       INPUT-OUTPUT SECTION.",
        "       FILE-CONTROL.",
        "           SELECT IN-F ASSIGN TO RPLIN.",
        "           SELECT OUT-F ASSIGN TO RPLOUT.",
        "       DATA DIVISION.",
        "       FILE SECTION.",
        "       FD  IN-F.",
        "       COPY PFXREC REPLACING ==:P:== BY ==CUST==.",
        "       FD  OUT-F.",
        "       01  OUT-REC.",
        "           05  OUT-ID   PIC X(4).",
        "       PROCEDURE DIVISION.",
        "           OPEN INPUT IN-F OUTPUT OUT-F",
        "           STOP RUN.",
    ])
    (tmp_path / "RPL.cbl").write_text(program)
    [p] = analyze(tmp_path)["programs"]
    files = {f["direction"]: f for f in p["files"]}
    assert files["input"]["layout"]["fields"][0]["name"] == "CUST-ID"
    assert files["output"]["layout"]["fields"][0]["name"] == "OUT-ID" and p["convertible"]
    for extra, reason in [("           EXEC SQL SELECT 1 INTO :X FROM T END-EXEC.", "EXEC SQL"),
                          ("           CALL 'NOWHERE' USING OUT-ID", "NOWHERE")]:
        (tmp_path / "RPL.cbl").write_text(program.replace("           STOP RUN.", extra + "\n           STOP RUN."))
        [p] = analyze(tmp_path)["programs"]
        assert not p["convertible"] and reason in p["notConvertibleReason"]
    (tmp_path / "RPL.cbl").write_text(program.replace("ASSIGN TO RPLIN.", "ASSIGN TO RPLIN\n               ORGANIZATION IS INDEXED\n               RECORD KEY IS CUST-ID."))
    [p] = analyze(tmp_path)["programs"]
    assert not p["convertible"] and "INDEXED" in p["notConvertibleReason"]


def test_several_record_types_are_reported():
    two = parse_copybook("       01  R1.\n           05  A  PIC X(3).\n       01  R2.\n           05  B  PIC 9(5).\n")
    assert two.as_dict() is None and "2 record types" in two.unsupported


def test_open_direction_is_not_overwritten_by_later_statements():
    from diocle_analyzer.cobol import parse_program
    code = "\n".join([
        "       IDENTIFICATION DIVISION.", "       PROGRAM-ID. TWO.", "       ENVIRONMENT DIVISION.",
        "       INPUT-OUTPUT SECTION.", "       FILE-CONTROL.", "           SELECT A-F ASSIGN TO AIN.",
        "           SELECT B-F ASSIGN TO BOUT.", "       PROCEDURE DIVISION.", "           OPEN INPUT A-F",
        "           OPEN OUTPUT B-F", "           PERFORM X", "           CLOSE A-F B-F", "           STOP RUN."])
    assert parse_program(code).directions == {"A-F": "input", "B-F": "output"}


def test_sort_using_giving_and_io_files():
    from diocle_analyzer.cobol import parse_program
    code = "\n".join([
        "       IDENTIFICATION DIVISION.", "       PROGRAM-ID. SRT.", "       ENVIRONMENT DIVISION.",
        "       INPUT-OUTPUT SECTION.", "       FILE-CONTROL.", "           SELECT IN-F ASSIGN TO SRTIN.",
        "           SELECT OUT-F ASSIGN TO SRTOUT.", "           SELECT WRK-F ASSIGN TO SORTWK.",
        "       DATA DIVISION.", "       FILE SECTION.", "       SD  WRK-F.", "       01  WRK-REC PIC X(10).",
        "       PROCEDURE DIVISION.", "           SORT WRK-F ON ASCENDING KEY WRK-REC",
        "               USING IN-F GIVING OUT-F", "           STOP RUN."])
    info = parse_program(code)
    assert info.directions == {"IN-F": "input", "OUT-F": "output"} and info.sort_files == {"WRK-F"}


def test_multi_file_programs_get_shared_sorted_keys():
    [p] = analyze(SAMPLES / "account-match")["programs"]
    assert p["convertible"] and sorted(f["direction"] for f in p["files"]) == ["input", "input", "output", "output"]
    from diocle_analyzer.analyze import shared_keys
    keys = shared_keys([f for f in p["files"] if f["direction"] == "input"])
    assert keys["sharedKeys"] == [[["MSTIN", "MS-ACCT-ID"], ["TXNIN", "TX-ACCT-ID"]]]


def test_second_review_shapes_are_rejected_or_detected():
    from diocle_analyzer.cobol import parse_program
    sync = parse_copybook("       01  R.\n           05  A  PIC X.\n           05  B  PIC S9(4) COMP SYNC.\n")
    assert sync.as_dict() is None and "SYNCHRONIZED" in sync.unsupported
    comp6 = parse_copybook("       01  R.\n           05  A  PIC 9(4) COMP-6.\n")
    assert comp6.as_dict() is None and "COMP-6" in comp6.unsupported
    head = "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. C.\n       PROCEDURE DIVISION.\n"
    assert parse_program(head + '           CALL "SUBX" USING A.\n').calls == ["SUBX"]
    dynamic = parse_program(head + "           CALL WS-PGM USING A.\n")
    assert dynamic.calls == [] and dynamic.dynamic_calls == ["WS-PGM"]


@pytest.mark.parametrize("sample", ["packed-posting", "account-match"])
def test_new_samples_validate_against_the_contract(sample):
    validate_report(analyze(SAMPLES / sample))


def test_jcl_procedures_symbolics_and_overrides():
    from diocle_analyzer.jcl import parse_jcl, parse_procs
    proc = ("//QMKINT   PROC ENV=PROD,GEN=+1\n//INT010   EXEC PGM=INTACCR\n"
            "//ACCTIN   DD DSN=QMK.&ENV..ACCT.EXTRACT,DISP=SHR\n"
            "//INTOUT   DD DSN=QMK.&ENV..INT.RESULT(&GEN),\n//            DISP=(NEW,CATLG)\n")
    procs = {p.name: p for p in parse_procs(proc)}
    assert parse_jcl(proc, "PROCLIB/QMKINT", procs) == []  # a procedure is not a job
    job = "//QMKD010  JOB (1),'X'\n//S1       EXEC QMKINT,ENV=TEST\n//INT010.ACCTIN DD DSN=QMK.OVERRIDE,DISP=SHR\n"
    [step] = parse_jcl(job, "JCLLIB/QMKD010", procs)
    assert step.program == "INTACCR" and step.job == "QMKD010"
    assert step.dsns == {"ACCTIN": "QMK.OVERRIDE", "INTOUT": "QMK.TEST.INT.RESULT(+1)"}


def test_mainframe_library_members_are_classified_by_content(tmp_path):
    from diocle_analyzer.analyze import classify
    (tmp_path / "QMK.PROD.COBOL").mkdir()
    (tmp_path / "QMK.PROD.COPYLIB").mkdir()
    (tmp_path / "DATA").mkdir()
    (tmp_path / "QMK.PROD.COBOL" / "PGMA").write_text(
        "       IDENTIFICATION DIVISION.                                         00000100\n"
        "       PROGRAM-ID. PGMA.                                                00000200\n")
    (tmp_path / "QMK.PROD.COPYLIB" / "RECA").write_text("       01  RECA.\n           05  A  PIC X.\n")
    (tmp_path / "DATA" / "QMK.PROD.EXTRACT").write_bytes(bytes.fromhex("C1C2F1F2D300"))
    programs, copybooks, jcl = classify(tmp_path)
    assert [p.name for p in programs] == ["PGMA"] and "RECA" in copybooks and not jcl
    assert not any(p.parent.name == "DATA" for p in copybooks.values())  # binary EBCDIC data is skipped
