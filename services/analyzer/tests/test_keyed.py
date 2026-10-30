"""Keyed (INDEXED) files: classification into ksds-subset-1, the exact refusal reasons, and the contract."""

import json
import re
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, validate_report, write_sample

SAMPLES = Path(__file__).resolve().parents[3] / "samples"

PROGRAM = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. KEYTEST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRAN-FILE ASSIGN TO TRANIN ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-FILE ASSIGN TO OUTF ORGANIZATION IS LINE SEQUENTIAL.
           SELECT KF ASSIGN TO KFILE
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS K-ID
               FILE STATUS IS FS.
       DATA DIVISION.
       FILE SECTION.
       FD  TRAN-FILE.
       01  TRAN-REC.
           05  T-ID               PIC X(4).
           05  T-DATA             PIC X(4).
       FD  OUT-FILE.
       01  OUT-REC.
           05  OUT-DATA           PIC X(8).
       FD  KF.
       01  K-REC.
           05  K-PRE              PIC X(2).
           05  K-ID               PIC X(4).
           05  K-DATA             PIC X(4).
       WORKING-STORAGE SECTION.
       01  FS                     PIC XX.
       PROCEDURE DIVISION.
           OPEN INPUT TRAN-FILE
           OPEN I-O KF
           OPEN OUTPUT OUT-FILE
           READ TRAN-FILE AT END MOVE SPACES TO TRAN-REC END-READ
           MOVE T-ID TO K-ID
           START KF KEY IS >= K-ID
           READ KF NEXT
           WRITE OUT-REC FROM K-DATA
           CLOSE TRAN-FILE KF OUT-FILE
           STOP RUN.
"""


def report_for(tmp_path, text):
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "KEYTEST.cbl").write_text(text)
    report = analyze(tmp_path)
    validate_report(report)
    return report["programs"][0]


def keyed(program):
    return next(f for f in program["files"] if f.get("keyed"))["keyed"]


def test_subset_program_is_convertible_with_key_facts(tmp_path):
    p = report_for(tmp_path, PROGRAM)
    assert p["convertible"], p["notConvertibleReason"]
    k = keyed(p)
    assert k["subset"] == "ksds-subset-1" and k["accessMode"] == "DYNAMIC" and k["fileStatus"] == "FS" and k["openMode"] == "I-O"
    assert k["recordKey"] == {"field": "K-ID", "offset": 2, "length": 4}
    assert next(f for f in p["files"] if f["dd"] == "KFILE")["direction"] == "io"


@pytest.mark.parametrize("edit, fragment", [
    (lambda s: s.replace("RECORD KEY IS K-ID", "RECORD KEY IS K-ID\n               ALTERNATE RECORD KEY IS K-DATA"), "ALTERNATE RECORD KEY is not supported"),
    (lambda s: s.replace("ALTERNATE", "ALTERNATE").replace("RECORD KEY IS K-ID", "RECORD KEY IS K-ID\n               ALTERNATE RECORD KEY IS K-DATA WITH DUPLICATES"), "ALTERNATE RECORD KEY is not supported"),
    (lambda s: s.replace("ORGANIZATION IS INDEXED", "ORGANIZATION IS RELATIVE"), "RELATIVE files are not supported"),
    (lambda s: s.replace("               FILE STATUS IS FS.", "               LOCK MODE IS AUTOMATIC\n               FILE STATUS IS FS."), "LOCK MODE"),
    (lambda s: s.replace("\n               FILE STATUS IS FS.", "."), "no FILE STATUS clause"),
    (lambda s: s.replace("START KF KEY IS >= K-ID", "START KF KEY IS < K-ID"), "START with KEY < is not supported"),
    (lambda s: s.replace("READ KF NEXT", "READ KF PREVIOUS"), "READ PREVIOUS is not supported"),
    (lambda s: s.replace("READ KF NEXT", "READ KF NEXT WITH LOCK"), "WITH LOCK is not supported"),
    (lambda s: s.replace("OPEN I-O KF", "OPEN EXTEND KF"), "OPEN EXTEND on a keyed file is not supported"),
    (lambda s: s.replace("OPEN I-O KF", "OPEN I-O KF\n           CLOSE KF\n           OPEN INPUT KF"), "opened more than one way"),
    (lambda s: s.replace("RECORD KEY IS K-ID", "RECORD KEY IS K-REC"), "not an elementary field"),
    (lambda s: s.replace("K-ID               PIC X(4).", "K-ID               PIC S9(4) COMP-3."), "signed, packed or binary"),
])
def test_each_refusal_has_its_exact_reason(tmp_path, edit, fragment):
    new = edit(PROGRAM)
    assert new != PROGRAM
    p = report_for(tmp_path, new)
    assert not p["convertible"] and fragment in p["notConvertibleReason"], p["notConvertibleReason"]
    assert p["notConvertibleReason"].startswith("keyed file ")


def test_keyed_file_with_exec_sql_is_refused(tmp_path):
    new = PROGRAM.replace("       PROCEDURE DIVISION.\n", "       PROCEDURE DIVISION.\n           EXEC SQL COMMIT END-EXEC\n")
    p = report_for(tmp_path, new)
    assert not p["convertible"]


def test_a_keyed_file_that_is_only_read_is_direction_input(tmp_path):
    p = report_for(tmp_path, PROGRAM.replace("OPEN I-O KF", "OPEN INPUT KF"))
    assert p["convertible"] and next(f for f in p["files"] if f["dd"] == "KFILE")["direction"] == "input"
    assert keyed(p)["openMode"] == "INPUT"


def test_the_alternate_key_sample_is_refused_with_the_exact_reason():
    report = analyze(SAMPLES / "vsam-alternate-key")
    validate_report(report)
    p = report["programs"][0]
    assert not p["convertible"] and "ALTERNATE RECORD KEY is not supported" in p["notConvertibleReason"]


def test_customer_update_sample_matches_its_sample_json(tmp_path):
    report = analyze(SAMPLES / "vsam-customer-update")
    validate_report(report)
    p = report["programs"][0]
    assert p["convertible"] and keyed(p)["recordKey"] == {"field": "CM-CUST-ID", "offset": 2, "length": 6}
    out = write_sample(SAMPLES / "vsam-customer-update", report, p, tmp_path)
    mine = json.loads((out / "sample.json").read_text())
    shipped = json.loads((SAMPLES / "vsam-customer-update" / "sample.json").read_text())
    for key in ("files", "ksds", "program", "source", "collation"):
        assert mine[key] == shipped[key], key
    assert shipped["ksds"]["keyLinks"] == [{"dd": "TRANIN", "field": "TR-CUST-ID", "keyedDd": "CUSTMAST"}]


def test_contract_accepts_old_reports_and_rejects_a_malformed_keyed_block(tmp_path):
    report = analyze(SAMPLES / "vsam-customer-update")
    for prog in report["programs"]:  # a v0.6 report has no keyed block at all
        for f in prog["files"]:
            f.pop("keyed", None)
    report["version"] = "0.6"
    validate_report(report)
    report = analyze(SAMPLES / "vsam-customer-update")
    next(f for f in report["programs"][0]["files"] if f.get("keyed"))["keyed"]["accessMode"] = "BACKWARDS"
    with pytest.raises(Exception):
        validate_report(report)


def test_select_optional_keeps_the_file_name_and_stays_in_the_subset(tmp_path):
    p = report_for(tmp_path, PROGRAM.replace("SELECT KF ASSIGN", "SELECT OPTIONAL KF ASSIGN"))
    assert p["convertible"], p["notConvertibleReason"]
    assert keyed(p)["recordKey"]["field"] == "K-ID"


def test_lowercase_select_clause_is_read_case_insensitively(tmp_path):
    new = PROGRAM.replace("SELECT KF ASSIGN TO KFILE", "select kf assign to kfile")
    p = report_for(tmp_path, new)
    assert p["convertible"], p["notConvertibleReason"]
    assert next(f for f in p["files"] if f.get("keyed"))["dd"] == "KFILE"


def test_keyed_file_whose_select_is_not_recognised_is_refused(tmp_path):
    p = report_for(tmp_path, PROGRAM.replace("ASSIGN TO KFILE", 'ASSIGN USING WS-NAME'))
    assert not p["convertible"]
    assert "not recognised" in p["notConvertibleReason"] or "could not read" in p["notConvertibleReason"]


def test_copy_inside_file_control_is_refused(tmp_path):
    p = report_for(tmp_path, PROGRAM.replace("           SELECT OUT-FILE", "           COPY SELCOPY.\n           SELECT OUT-FILE"))
    assert not p["convertible"] and "FILE-CONTROL contains a COPY" in p["notConvertibleReason"]


def test_read_invalid_key_is_not_an_alternate_key_read(tmp_path):
    new = PROGRAM.replace("READ KF NEXT\n", "READ KF INVALID KEY MOVE SPACES TO K-DATA END-READ\n")
    assert new != PROGRAM
    p = report_for(tmp_path, new)
    assert p["convertible"], p["notConvertibleReason"]


def test_read_with_key_is_still_an_alternate_key_read(tmp_path):
    p = report_for(tmp_path, PROGRAM.replace("READ KF NEXT", "READ KF KEY IS K-DATA"))
    assert not p["convertible"] and "alternate key" in p["notConvertibleReason"]
