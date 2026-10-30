"""EXEC SQL: the verified subset, exact refusal reasons, and where the schema may come from."""
import json
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze, validate_report, write_sample

ROOT = Path(__file__).resolve().parents[3]
HEAD = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. P.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT OUT-FILE ASSIGN TO OUTDD ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  OUT-FILE.
       COPY OUTREC.
       WORKING-STORAGE SECTION.
{ws}
       01  WS-ID                   PIC X(8).
       01  WS-BAL                  PIC S9(7)V99 COMP-3.
       01  WS-GROUP.
           05  WS-G1               PIC X.
       PROCEDURE DIVISION.
           OPEN OUTPUT OUT-FILE
{body}
           CLOSE OUT-FILE
           STOP RUN.
"""
DECL = """           EXEC SQL DECLARE ACCT TABLE
               ( ID CHAR(8) NOT NULL, BAL DECIMAL(9,2) NOT NULL )
           END-EXEC."""
SQLCA = "           EXEC SQL INCLUDE SQLCA END-EXEC."


def report(tmp_path, body, ws=None, extra=None):
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    (repo / "OUTREC.cpy").write_text("       01  OUT-REC.\n           05  OUT-TEXT            PIC X(10).\n")
    (repo / "P.cbl").write_text(HEAD.format(ws=ws if ws is not None else SQLCA + "\n" + DECL, body=body))
    for name, text in (extra or {}).items():
        (repo / name).write_text(text)
    r = analyze(repo)
    validate_report(r)
    return r["programs"][0]


def stmt(sql):
    words, lines, cur = sql.split(), [], "           EXEC SQL"
    for w in words + ["END-EXEC"]:
        if len(cur) + 1 + len(w) > 70:
            lines.append(cur)
            cur = "               "
        cur += " " + w
    return "\n".join(lines + [cur]) + "\n"


def test_subset_program_is_convertible_with_facts(tmp_path):
    body = (stmt("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID") + stmt("UPDATE ACCT SET BAL = BAL + :WS-BAL WHERE ID = :WS-ID")
            + stmt("INSERT INTO ACCT (ID, BAL) VALUES (:WS-ID, 5.25)") + stmt("DELETE FROM ACCT WHERE BAL < 0") + stmt("COMMIT"))
    p = report(tmp_path, body)
    assert p["convertible"] and p["notConvertibleReason"] is None
    assert p["sql"]["refusal"] is None
    assert [t["name"] for t in p["sql"]["tables"]] == ["ACCT"]
    assert {s["kind"] for s in p["sql"]["statements"]} >= {"select-into", "update", "insert", "delete", "commit"}


@pytest.mark.parametrize("sql, fragment", [
    ("PREPARE S1 FROM :WS-ID", "dynamic SQL (PREPARE)"),
    ("SELECT BAL INTO :WS-BAL FROM ACCT A JOIN ACCT B ON 1 = 1 WHERE ID = :WS-ID", "outside the verified subset"),
    ("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID FETCH FIRST 1 ROW ONLY", "FETCH FIRST"),
    ("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID WITH UR", "WITH"),
    ("SELECT UPPER(ID) INTO :WS-ID FROM ACCT", "'UPPER'"),
    ("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = CURRENT DATE", "CURRENT"),
    ("SELECT BAL INTO :WS-NOPE FROM ACCT", "not defined"),
    ("SELECT BAL INTO :WS-GROUP FROM ACCT", "group item"),
    ("SELECT BAL INTO :WS-ID FROM ACCT", "alphanumeric"),
    ("SELECT BAL INTO :WS-BAL FROM NOPE", "no DECLARE TABLE"),
    ("CALL PROC1 (:WS-ID)", "stored procedure"),
    ("DECLARE C1 CURSOR FOR SELECT ID FROM ACCT", "without ORDER BY"),
    ("DECLARE C1 CURSOR WITH HOLD FOR SELECT ID FROM ACCT ORDER BY ID", "WITH HOLD"),
    ("INSERT INTO ACCT (ID) VALUES (:WS-ID)", "must supply every column"),
    ("UPDATE ACCT SET BAL = BAL * 2", "outside the verified subset"),
    ("WHENEVER SQLERROR GO TO ERR", "WHENEVER"),
    ("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID FOR UPDATE", "FOR UPDATE"),
])
def test_each_refusal_has_its_exact_reason(tmp_path, sql, fragment):
    p = report(tmp_path, stmt(sql))
    assert not p["convertible"]
    assert fragment in p["notConvertibleReason"]
    assert p["notConvertibleReason"].startswith("EXEC SQL outside the verified subset (db2-subset-1): line ")


def test_no_schema_is_never_guessed(tmp_path):
    p = report(tmp_path, stmt("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID"), ws=SQLCA)
    assert not p["convertible"] and "never guessed" in p["notConvertibleReason"]


def test_sqlca_is_required_and_sqlstate_is_refused(tmp_path):
    p = report(tmp_path, stmt("COMMIT"), ws=DECL)
    assert "INCLUDE SQLCA is required" in p["notConvertibleReason"]
    p = report(tmp_path, stmt("COMMIT") + "           DISPLAY SQLSTATE\n")
    assert "SQLSTATE" in p["notConvertibleReason"]


def test_schema_from_ddl_file_and_dclgen(tmp_path):
    ddl = "CREATE TABLE ACCT (ID CHAR(8) NOT NULL PRIMARY KEY, BAL DECIMAL(9,2) NOT NULL);\n"
    p = report(tmp_path, stmt("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID"), ws=SQLCA, extra={"schema.sql": ddl})
    assert p["convertible"]
    assert p["sql"]["tables"][0]["source"] == "ddl" and p["sql"]["tables"][0]["primaryKey"] == ["ID"]
    dcl = ("           EXEC SQL DECLARE ACCT TABLE\n           ( ID CHAR(8) NOT NULL, BAL DECIMAL(9,2) NOT NULL )\n"
           "           END-EXEC.\n")
    p = report(tmp_path, stmt("SELECT BAL INTO :WS-BAL FROM ACCT WHERE ID = :WS-ID"),
               ws=SQLCA + "\n           EXEC SQL INCLUDE ACCTDCL END-EXEC.", extra={"ACCTDCL.cpy": dcl})
    assert p["convertible"] and p["sql"]["tables"][0]["source"] == "dclgen"
    assert p["sql"]["tables"][0]["path"] == "ACCTDCL.cpy" and "ACCTDCL" in p["copybooks"]


def test_unsupported_column_types_are_refused(tmp_path):
    decl = "           EXEC SQL DECLARE ACCT TABLE\n           ( ID CHAR(8) NOT NULL, BAL DECIMAL(9,2), D DATE )\n           END-EXEC."
    p = report(tmp_path, stmt("SELECT BAL INTO :WS-BAL FROM ACCT"), ws=SQLCA + "\n" + decl)
    assert not p["convertible"] and "DATE" in p["notConvertibleReason"]


def test_cics_stays_refused_and_out_of_scope(tmp_path):
    p = report(tmp_path, "           EXEC CICS RETURN END-EXEC\n")
    assert not p["convertible"] and "CICS and IMS are out of scope" in p["notConvertibleReason"]


def test_sample_report_and_sample_json(tmp_path):
    root = ROOT / "samples" / "db2-account-report"
    r = analyze(root)
    validate_report(r)
    p = r["programs"][0]
    assert p["convertible"] and "ACCTDCL" in p["copybooks"]
    meta = json.loads((write_sample(root, r, p, tmp_path) / "sample.json").read_text())
    assert meta["sql"]["seedRows"] == {"AUDIT": 0}  # nothing reads AUDIT: seeded empty
    assert {(l["table"], l["column"]) for l in meta["sql"]["keyLinks"]} >= {("ACCOUNTS", "ACCT_ID")}
    assert "layouts" not in meta and len(meta["files"]) == 2


def test_refused_sample_in_repo():
    r = analyze(ROOT / "samples" / "db2-dynamic-sql")
    p = r["programs"][0]
    assert not p["convertible"] and "dynamic SQL (PREPARE)" in p["notConvertibleReason"]


def test_old_report_without_sql_is_still_valid():
    r = analyze(ROOT / "samples" / "display-report")
    assert "sql" not in r["programs"][0]
    validate_report(r)
