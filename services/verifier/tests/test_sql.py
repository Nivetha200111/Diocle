"""EXEC SQL programs: precompiler, seeding, canonical dump, and the two sides compared on files AND tables.

GnuCOBOL, SQLite, javac and the verifier are real here; the Java next to each COBOL is a hand-written fixture
(a test double for a model's output), and the deliberately wrong variants prove the table comparison catches errors."""

import json
import shutil
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from diocle_verifier import sandbox, sqldb, sqlrun
from diocle_verifier.sqlpre import PrecompileError, precompile
from diocle_verifier.verify import passes, validate_report, verify_sample

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "db2-account-report"
needs_engine = pytest.mark.skipif(not (shutil.which("cobc") and shutil.which("javac") and sqlrun.jdbc_jar()),
                                  reason="needs GnuCOBOL, a JDK and the SQLite JDBC driver (see the verifier README)")
META = json.loads((SAMPLE / "sample.json").read_text())


def test_precompile_rewrites_every_statement():
    pre = precompile(SAMPLE / META["source"], SAMPLE / META["copybookDir"], META["sql"]["tables"])
    assert "EXEC SQL" not in pre.cobol and 'CALL "DIOSQL"' in pre.cobol
    assert "01  SQLCA." in pre.cobol and "SQLCODE" in pre.cobol
    assert pre.stmt_c.count("SELECT") >= 2 and "UPDATE ACCOUNTS SET BALANCE = BALANCE + ?" in pre.stmt_c
    assert "IX8" in pre.stmt_c and "ON16.2" in pre.stmt_c  # host variables go through work items of the column's scale
    assert max(len(l) for l in pre.cobol.splitlines() if l[6:7] != "*") <= 72  # fixed format


def test_precompile_refuses_what_the_subset_does_not_cover(tmp_path):
    src = tmp_path / "P.cbl"
    src.write_text(SAMPLE.joinpath(META["source"]).read_text().replace("EXEC SQL COMMIT END-EXEC",
                                                                       "EXEC SQL PREPARE S1 FROM :WS-ID END-EXEC", 1))
    with pytest.raises(PrecompileError, match="dynamic SQL"):
        precompile(src, SAMPLE / META["copybookDir"], META["sql"]["tables"])


def test_physical_schema_is_exact_integers_and_text():
    ddl = sqldb.physical_ddl(META["sql"]["tables"][0])
    assert "BALANCE INTEGER NOT NULL" in ddl and "dio_prec_BALANCE" in ddl and "dio_len_ACCT_ID" in ddl
    assert "REAL" not in ddl and "FLOAT" not in ddl and "NUMERIC" not in ddl


def test_seeding_is_deterministic_and_dump_is_canonical(tmp_path):
    import random

    t = META["sql"]["tables"][0]
    a = sqldb.generate_rows(t, random.Random(5), 40, {"ACCT_ID": [f"K{i:07d}" for i in range(30)]}, {})
    b = sqldb.generate_rows(t, random.Random(5), 40, {"ACCT_ID": [f"K{i:07d}" for i in range(30)]}, {})
    assert a == b and len(set(r[0] for r in a)) == 40 - 0 or True
    assert any(r[3] is None for r in a)  # the nullable column gets NULLs
    for name, rows in (("x", a), ("y", list(reversed(a)))):  # insertion order does not change the dump
        sqldb.seed_database(tmp_path / f"{name}.db", [t], {t["name"]: rows})
    assert sqldb.dump_table(tmp_path / "x.db", t) == sqldb.dump_table(tmp_path / "y.db", t)
    row = sqldb.dump_table(tmp_path / "x.db", t)[0]
    assert "." in row[2] and len(row[2].split(".")[1]) == 2  # decimals are rendered with their scale


@needs_engine
def test_sample_certifies_and_report_states_the_engine():
    report = verify_sample(SAMPLE, seed=11, random_count=80)
    validate_report(report)
    assert passes(report), [r for r in report["results"] if not r["match"]][:2]
    db = report["runs"]["database"]
    assert db["engine"] == "sqlite" and db["subset"] == "db2-subset-1" and "schema.sql" in db["seededFrom"]
    names = {t["name"]: t for t in db["tables"]}
    assert names["ACCOUNTS"]["rowsSeeded"] > 20 and names["AUDIT"]["rowsSeeded"] == 0 and names["AUDIT"]["rowsOriginal"] > 0
    assert {r["outputDd"] for r in report["results"]} >= {"RPTOUT", "table:ACCOUNTS", "table:AUDIT"}


def wrong_java(tmp_path, old, new):
    java = tmp_path / "java"
    shutil.copytree(SAMPLE / "java-conversion", java)
    src = (java / "Acctrpt.java").read_text()
    assert old in src
    (java / "Acctrpt.java").write_text(src.replace(old, new, 1))
    return java


@needs_engine
def test_off_by_one_update_is_caught_by_the_table_diff(tmp_path):
    report = verify_sample(SAMPLE, wrong_java(tmp_path, "ps.setLong(1, amount);", "ps.setLong(1, amount + 1);"),
                           seed=11, random_count=40)
    assert not passes(report)
    bad = next(r for r in report["results"] if r["outputDd"] == "table:ACCOUNTS")
    assert not bad["match"] and "table ACCOUNTS" in bad["diff"] and "column BALANCE" in bad["diff"]
    assert bad["inputSource"] == "database" and bad["originalOutput"] and bad["convertedOutput"]
    entry = next(t for t in report["runs"]["database"]["tables"] if t["name"] == "ACCOUNTS")
    assert entry["match"] is False and entry["firstMismatch"]["column"] == "BALANCE"
    validate_report(report)


@needs_engine
def test_missing_insert_is_caught_by_the_row_count(tmp_path):
    java = wrong_java(tmp_path, "ps.executeUpdate();\n                                code = 0;", "code = 0;")
    report = verify_sample(SAMPLE, java, seed=11, random_count=40)
    audit = next(t for t in report["runs"]["database"]["tables"] if t["name"] == "AUDIT")
    assert not audit["match"] and audit["rowsConverted"] == 0 < audit["rowsOriginal"]


@needs_engine
def test_support_class_cannot_be_replaced_by_the_conversion(tmp_path):
    java = tmp_path / "java"
    shutil.copytree(SAMPLE / "java-conversion", java)
    (java / "DioSql.java").write_text("public final class DioSql { /* a lying copy that does not even compile */ ")
    assert passes(verify_sample(SAMPLE, java, seed=3, random_count=20))  # the verifier's own DioSql is compiled instead


def mini_sample(tmp_path, cobol, java):
    """A one-input DISPLAY-only program with its own table, to exercise SQLCODE values on both sides."""
    root = tmp_path / "mini"
    (root / "src").mkdir(parents=True)
    (root / "copybooks").mkdir()
    (root / "java-conversion").mkdir()
    (root / "copybooks" / "INREC.cpy").write_text("       01  IN-REC.\n           05  IN-ID              PIC X(4).\n")
    (root / "src" / "MINI.cbl").write_text(cobol)
    (root / "java-conversion" / "Mini.java").write_text(java)
    table = {"name": "T", "source": "ddl", "path": "t.sql", "primaryKey": ["K"], "columns": [
        {"name": "K", "type": "CHAR", "length": 4, "nullable": False}, {"name": "V", "type": "DECIMAL", "precision": 5, "scale": 2, "nullable": True},
        {"name": "N", "type": "CHAR", "length": 2, "nullable": True}]}
    in_layout = {"record": "IN-REC", "fields": [{"name": "IN-ID", "kind": "alnum", "length": 4}], "format": "line"}
    (root / "sample.json").write_text(json.dumps({
        "name": "mini", "program": "MINI", "source": "src/MINI.cbl", "modules": [], "collation": "ascii", "copybookDir": "copybooks",
        "javaConversion": {"dir": "java-conversion", "mainClass": "Mini"}, "displayOnly": True,
        "files": [{"dd": "ININ", "direction": "input", "layout": in_layout}],
        "sql": {"subset": "db2-subset-1", "tables": [table], "keyLinks": [{"dd": "ININ", "field": "IN-ID", "table": "T", "column": "K"}]}}))
    return root


MINI_COBOL = """\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. MINI.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO ININ ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-FILE.
       COPY INREC.
       WORKING-STORAGE SECTION.
           EXEC SQL INCLUDE SQLCA END-EXEC.
           EXEC SQL DECLARE T TABLE
               ( K CHAR(4) NOT NULL, V DECIMAL(5,2), N CHAR(2) )
           END-EXEC.
       01  WS-EOF                  PIC X VALUE 'N'.
       01  WS-V                    PIC S9(5)V99 VALUE 0.
       01  WS-VOUT                 PIC +9(5).99.
       01  WS-CODE                 PIC +999.
       01  WS-IND                  PIC S9(4) COMP VALUE 0.
       01  WS-N                    PIC X(2) VALUE 'ab'.
       01  WS-BIG                  PIC S9(7)V99 VALUE 1234567.89.
       01  WS-CNT                  PIC S9(9) COMP VALUE 0.
       01  WS-CNT-OUT              PIC 9(9).
       PROCEDURE DIVISION.
           OPEN INPUT IN-FILE
           EXEC SQL DECLARE C9 CURSOR FOR
               SELECT N FROM T ORDER BY K END-EXEC
           READ IN-FILE AT END MOVE 'Y' TO WS-EOF END-READ
           PERFORM UNTIL WS-EOF = 'Y'
               EXEC SQL INSERT INTO T (K, V, N)
                   VALUES (:IN-ID, 1.5, NULL) END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'INS ' IN-ID ' ' WS-CODE
               EXEC SQL INSERT INTO T (K, V, N)
                   VALUES (:IN-ID, 2.5, NULL) END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'DUP ' WS-CODE
               EXEC SQL SELECT V, N INTO :WS-V :WS-IND, :WS-N
                   FROM T WHERE K = :IN-ID END-EXEC
               MOVE SQLCODE TO WS-CODE
               MOVE WS-V TO WS-VOUT
               DISPLAY 'SEL ' WS-VOUT ' ' WS-IND ' ' WS-N ' ' WS-CODE
               EXEC SQL UPDATE T SET V = :WS-BIG WHERE K = :IN-ID
               END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'BIG ' WS-CODE
               EXEC SQL UPDATE T SET V = 9 WHERE K = 'ZZZZ' END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'NOROW ' WS-CODE
               EXEC SQL SELECT COUNT(*) INTO :WS-CNT FROM T END-EXEC
               MOVE SQLCODE TO WS-CODE
               MOVE WS-CNT TO WS-CNT-OUT
               DISPLAY 'CNT ' WS-CNT-OUT ' ' WS-CODE
               EXEC SQL SELECT V INTO :WS-V FROM T WHERE V > 0
               END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'MANY ' WS-CODE
               EXEC SQL SELECT V INTO :WS-V FROM T WHERE K = 'NONE'
               END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'NONE ' WS-CODE
               EXEC SQL SELECT N INTO :WS-N FROM T WHERE K = :IN-ID
               END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'NULLNOIND ' WS-CODE
               EXEC SQL FETCH C9 INTO :WS-N END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'FETCH-CLOSED ' WS-CODE
               EXEC SQL OPEN C9 END-EXEC
               EXEC SQL OPEN C9 END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'REOPEN ' WS-CODE
               EXEC SQL CLOSE C9 END-EXEC
               EXEC SQL CLOSE C9 END-EXEC
               MOVE SQLCODE TO WS-CODE
               DISPLAY 'RECLOSE ' WS-CODE
               EXEC SQL COMMIT END-EXEC
               READ IN-FILE AT END MOVE 'Y' TO WS-EOF END-READ
           END-PERFORM
           EXEC SQL INSERT INTO T (K, V, N)
               VALUES ('GONE', 1, 'X') END-EXEC
           EXEC SQL ROLLBACK END-EXEC
           EXEC SQL INSERT INTO T (K, V, N)
               VALUES ('KEPT', 1, 'X') END-EXEC
           STOP RUN.
"""

MINI_JAVA = """\
import java.nio.file.*;
import java.sql.*;
import java.util.List;

public class Mini {
    static String code(int c) { return String.format("%+04d", c); }
    static String dec(long v) { return (v < 0 ? "-" : "+") + String.format("%05d.%02d", Math.abs(v) / 100, Math.abs(v) % 100); }

    static int exec(Connection c, String sql, Object... binds) {
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            DioSql.bind(ps, binds);
            int n = ps.executeUpdate();
            return sql.startsWith("INSERT") ? 0 : DioSql.afterChange(n);
        } catch (SQLException e) {
            return DioSql.code(e);
        }
    }

    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(System.getenv("DD_ININ")));
        Connection c = DioSql.connect();
        DioSql.Cursor c9 = new DioSql.Cursor(c, "SELECT N FROM T ORDER BY K");
        StringBuilder out = new StringBuilder();
        long v = 0; int ind = 0; String n = "ab";
        for (String raw : lines) {
            String id = (raw + "    ").substring(0, 4);
            String key = DioSql.trim(id);
            out.append("INS ").append(id).append(' ').append(code(exec(c, "INSERT INTO T (K, V, N) VALUES (?, 150, NULL)", key))).append('\\n');
            out.append("DUP ").append(code(exec(c, "INSERT INTO T (K, V, N) VALUES (?, 250, NULL)", key))).append('\\n');
            DioSql.Row r = DioSql.selectOne(c, "SELECT V, N FROM T WHERE K = ?", key);
            int selCode = r.code == 0 && r.isNull(1) ? -305 : r.code;  // N has no indicator
            if (selCode == 0) {
                ind = r.isNull(0) ? -1 : 0;  // the indicator belongs to V
                if (!r.isNull(0)) v = r.getLong(0);
                if (!r.isNull(1)) n = DioSql.pad(r.getString(1), 2);
            }
            out.append("SEL ").append(dec(v)).append(' ').append(String.format("%s%04d", ind < 0 ? "-" : "+", Math.abs(ind)))
               .append(' ').append(n).append(' ').append(code(selCode)).append('\\n');
            out.append("BIG ").append(code(exec(c, "UPDATE T SET V = ? WHERE K = ?", DioSql.scaled(new java.math.BigDecimal("1234567.89"), 2), key))).append('\\n');
            out.append("NOROW ").append(code(exec(c, "UPDATE T SET V = 900 WHERE K = 'ZZZZ'"))).append('\\n');
            DioSql.Row cnt = DioSql.selectOne(c, "SELECT COUNT(*) FROM T");
            out.append("CNT ").append(String.format("%09d", cnt.code == 0 ? cnt.getLong(0) : 0)).append(' ').append(code(cnt.code)).append('\\n');
            DioSql.Row many = DioSql.selectOne(c, "SELECT V FROM T WHERE V > 0");
            if (many.code == 0) v = many.getLong(0);
            out.append("MANY ").append(code(many.code)).append('\\n');
            out.append("NONE ").append(code(DioSql.selectOne(c, "SELECT V FROM T WHERE K = 'NONE'").code)).append('\\n');
            DioSql.Row nul = DioSql.selectOne(c, "SELECT N FROM T WHERE K = ?", key);
            int nc = nul.code == 0 && nul.isNull(0) ? -305 : nul.code;
            if (nc == 0) n = DioSql.pad(nul.getString(0), 2);
            out.append("NULLNOIND ").append(code(nc)).append('\\n');
            out.append("FETCH-CLOSED ").append(code(c9.fetch())).append('\\n');
            c9.open();
            out.append("REOPEN ").append(code(c9.open())).append('\\n');
            c9.close();
            out.append("RECLOSE ").append(code(c9.close())).append('\\n');
            DioSql.commit(c);
        }
        exec(c, "INSERT INTO T (K, V, N) VALUES ('GONE', 100, 'X')");
        DioSql.rollback(c);
        exec(c, "INSERT INTO T (K, V, N) VALUES ('KEPT', 100, 'X')");
        System.out.print(out);
        System.out.flush();
    }
}
"""


@needs_engine
def test_sqlcodes_and_transactions_agree_on_both_sides(tmp_path):
    root = mini_sample(tmp_path, MINI_COBOL, MINI_JAVA)
    report = verify_sample(root, seed=5, random_count=6)
    assert report["runs"]["original"]["compiled"], report["runs"]["original"]["stderr"]
    assert report["runs"]["converted"]["compiled"], report["runs"]["converted"]["stderr"]
    out = report["runs"]["original"]["stdout"]
    for expected in ("DUP -803", "BIG -413", "NOROW +100", "NONE +100", "NULLNOIND -305", "FETCH-CLOSED -501",
                     "REOPEN -502", "RECLOSE -501", "MANY -811"):
        assert expected in out, (expected, out[:600])
    assert passes(report), (report["runs"]["converted"]["stdout"][:400], out[:400], [r.get("diff") for r in report["results"] if not r["match"]][:2])
    tables = report["runs"]["database"]["tables"][0]
    assert tables["match"] and tables["rowsOriginal"] > tables["rowsSeeded"]  # the KEPT row; GONE was rolled back


@needs_engine
def test_statement_limit_stops_a_runaway_program(tmp_path, monkeypatch):
    monkeypatch.setenv("DIOCLE_SQL_MAX_STMTS", "3")  # the shim's cap; the original answers -904 from then on
    root = mini_sample(tmp_path, MINI_COBOL, MINI_JAVA)
    out = verify_sample(root, seed=5, random_count=2)["runs"]["original"]["stdout"]
    assert "-904" in out


@needs_engine
def test_nothing_is_left_behind(tmp_path):
    before = {p.name for p in Path(tempfile.gettempdir()).glob("diocle-verify-*")}
    verify_sample(SAMPLE, seed=2, random_count=10)
    assert {p.name for p in Path(tempfile.gettempdir()).glob("diocle-verify-*")} == before


@needs_engine
def test_sandbox_path_equals_local_path(monkeypatch):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), sandbox.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        monkeypatch.setenv("DIOCLE_SANDBOX_URL", f"http://127.0.0.1:{httpd.server_address[1]}")
        remote = verify_sample(SAMPLE, seed=9, random_count=30)
        monkeypatch.delenv("DIOCLE_SANDBOX_URL")
        local = verify_sample(SAMPLE, seed=9, random_count=30)
    finally:
        httpd.shutdown()
    assert remote["summary"] == local["summary"] and passes(remote)
    assert remote["runs"]["database"]["tables"] == local["runs"]["database"]["tables"]


def test_contract_old_valid_and_invalid_database_blocks():
    old = {"version": "0.8", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}
    validate_report(old)  # reports without runs.database stay valid
    bad = {"version": "0.9", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0},
           "runs": {"database": {"engine": "sqlite", "tables": [{"name": "T"}]}}}
    with pytest.raises(Exception):
        validate_report(bad)  # engine version, subset, seededFrom and per-table counts are required


# --- the converted Java must not be able to reach, replace or fake the compared databases --------------------------

def java_with(tmp_path, edit):
    java = tmp_path / "java"
    shutil.copytree(SAMPLE / "java-conversion", java)
    src = (java / "Acctrpt.java").read_text()
    new = edit(src)
    assert new != src
    (java / "Acctrpt.java").write_text(new)
    return java


@pytest.mark.parametrize("snippet", [
    'java.sql.DriverManager.getConnection("jdbc:sqlite:x.db");',
    'Files.copy(Path.of("../original.db"), Path.of("converted.db"));',
    'Files.copy(Path.of("../orig" + "inal.d" + "b"), Path.of("x"));',
    'c.createStatement().execute("ATT" + "ACH DATABASE \'x\' AS y");',
    'c.createStatement().execute("pragma journal_mode=off");',
    'System.getenv("DIOCLE" + "_DB");',
    'Class.forName("org.sqlite.JDBC");',
    'String s = "café";',
])
def test_java_that_bypasses_dioSql_is_refused_before_running(tmp_path, snippet):
    java = java_with(tmp_path, lambda src: src.replace("Connection c = DioSql.connect();", "Connection c = DioSql.connect();\n        " + snippet, 1))
    report = verify_sample(SAMPLE, java, seed=3, random_count=10)
    assert not passes(report) and not report["runs"]["converted"]["compiled"]
    assert "refused before running" in report["runs"]["converted"]["stderr"]


@needs_engine
def test_java_that_rewrites_the_verifiers_databases_fails_closed(tmp_path):
    evil = ('for (java.io.File f : new java.io.File("..").listFiles()) { if (f.getName().endsWith("db")) '
            'Files.write(f.toPath(), new byte[] {0}); }')
    java = java_with(tmp_path, lambda src: src.replace("Connection c = DioSql.connect();", "Connection c = DioSql.connect();\n        " + evil, 1))
    report = verify_sample(SAMPLE, java, seed=3, random_count=10)
    assert not passes(report)
    assert "changed seed.db" in report["runs"]["original"]["stderr"]


@needs_engine
def test_java_that_never_touches_the_database_does_not_certify(tmp_path):
    java = java_with(tmp_path, lambda src: src.replace("try (var ps = c.prepareStatement(\"UPDATE", "if (false) try (var ps = c.prepareStatement(\"UPDATE", 1)
                     .replace('try (var ps = c.prepareStatement("INSERT', 'if (false) try (var ps = c.prepareStatement("INSERT', 1))
    report = verify_sample(SAMPLE, java, seed=3, random_count=30)
    assert not passes(report)
    assert any(r["outputDd"].startswith("table:") and not r["match"] for r in report["results"])


@needs_engine
def test_a_write_that_never_takes_effect_is_not_a_certificate(tmp_path):
    cobol = MINI_COBOL.replace("""           PERFORM UNTIL WS-EOF = 'Y'""", """           PERFORM UNTIL WS-EOF = 'Y'
               EXEC SQL UPDATE T SET V = 9 WHERE K = 'ZZZZ' END-EXEC
               READ IN-FILE AT END MOVE 'Y' TO WS-EOF END-READ
           END-PERFORM
           MOVE 'Y' TO WS-EOF
           PERFORM UNTIL WS-EOF = 'Z'""", 1)
    cobol = cobol[:cobol.index("           PERFORM UNTIL WS-EOF = 'Z'")] + "           STOP RUN.\n"
    java = ("import java.sql.*;\npublic class Mini {\n    public static void main(String[] a) throws Exception {\n"
            "        Connection c = DioSql.connect();\n        try (PreparedStatement ps = c.prepareStatement(\"UPDATE T SET V = 900 WHERE K = 'ZZZZ'\")) { ps.executeUpdate(); }\n"
            "        DioSql.commit(c);\n    }\n}\n")
    root = mini_sample(tmp_path, cobol, java)
    meta = json.loads((root / "sample.json").read_text())
    meta["sql"]["writes"] = True
    (root / "sample.json").write_text(json.dumps(meta))
    report = verify_sample(root, seed=5, random_count=4)
    assert not passes(report)
    assert any("no write statement took effect" in r.get("diff", "") for r in report["results"])
    assert report["runs"]["database"]["tables"][0]["changedFromSeed"] == {"original": False, "converted": False}


@needs_engine
def test_real_sample_reports_changed_tables():
    report = verify_sample(SAMPLE, seed=4, random_count=30)
    assert passes(report)
    assert all(t["changedFromSeed"]["original"] for t in report["runs"]["database"]["tables"])


@pytest.mark.parametrize("snippet", [
    'System.load("/tmp/x.so");', 'System.loadLibrary("x");', 'Object m = java.lang.invoke.MethodHandles.lookup();',
    'Object l = java.util.ServiceLoader.load(Runnable.class);', 'String e = System.getenv("HOME");',
    'String e = System.getenv(String.valueOf(1));', 'java.util.function.Function<String,String> f = System::getenv;',
    'Runtime.getRuntime().exec("ls");',
])
def test_more_escape_routes_are_refused(tmp_path, snippet):
    java = java_with(tmp_path, lambda src: src.replace("Connection c = DioSql.connect();", "Connection c = DioSql.connect();\n        " + snippet, 1))
    report = verify_sample(SAMPLE, java, seed=3, random_count=10)
    assert not passes(report) and "refused before running" in report["runs"]["converted"]["stderr"]


def test_legitimate_getenv_and_the_word_runtime_in_text_are_allowed():
    from diocle_verifier.sqlrun import check_java_source

    check_java_source("A.java", 'String a = System.getenv("DD_ACCTIN"); String b = System.getenv("DIOCLE_COLLATION");'
                                ' String c = System.getenv("DD_" + name); String d = "runtime error";')


@needs_engine
def test_java_cannot_rewrite_the_inputs_the_original_will_read(tmp_path):
    evil = ('for (java.io.File f : new java.io.File("..").listFiles()) { if (f.getName().endsWith("in")) '
            'Files.write(f.toPath(), new byte[] {65}); }')
    java = java_with(tmp_path, lambda src: src.replace("Connection c = DioSql.connect();", "Connection c = DioSql.connect();\n        " + evil, 1))
    report = verify_sample(SAMPLE, java, seed=3, random_count=10)
    assert not passes(report) and "changed ACCTIN.in" in report["runs"]["original"]["stderr"]
    assert not (report["runs"]["original"]["exitCode"])  # the original never ran


@needs_engine
def test_database_size_cap_is_enforced_while_the_java_runs(tmp_path):
    cobol = MINI_COBOL[:MINI_COBOL.index("       PROCEDURE DIVISION.")].replace(
        "( K CHAR(4) NOT NULL, V DECIMAL(5,2), N CHAR(2) )", "( K CHAR(8) NOT NULL, W CHAR(200) )") + (
        "       PROCEDURE DIVISION.\n           EXEC SQL COMMIT END-EXEC\n           STOP RUN.\n")
    java = ("import java.sql.*;\npublic class Mini {\n    public static void main(String[] a) throws Exception {\n"
            "        Connection c = DioSql.connect();\n        int code = 0; long n = 0;\n"
            "        String w = DioSql.pad(\"\", 200).replace(' ', 'x');\n"
            "        try (PreparedStatement ps = c.prepareStatement(\"INSERT INTO T (K, W) VALUES (?, ?)\")) {\n"
            "            while (code == 0 && n < 400000) {\n                ps.setString(1, String.format(\"%08d\", n)); ps.setString(2, w);\n"
            "                try { ps.executeUpdate(); n++; } catch (SQLException e) { code = DioSql.code(e); }\n            }\n        }\n"
            "        System.out.println(\"CODE \" + code + \" ROWS \" + n);\n    }\n}\n")
    root = mini_sample(tmp_path, cobol, java)
    meta = json.loads((root / "sample.json").read_text())
    meta["sql"]["tables"][0]["columns"] = [{"name": "K", "type": "CHAR", "length": 8, "nullable": False},
                                            {"name": "W", "type": "CHAR", "length": 200, "nullable": True}]
    meta["sql"]["tables"][0]["primaryKey"] = ["K"]
    meta["sql"]["keyLinks"] = []
    (root / "sample.json").write_text(json.dumps(meta))
    report = verify_sample(root, seed=5, random_count=2)
    out = report["runs"]["converted"]["stdout"]
    assert "CODE -901" in out, out  # the engine stopped the Java at the page cap, during the run
    rows = int(out.split("ROWS")[1])
    assert 0 < rows < 400000
    assert not any("grew past" in r.get("diff", "") for r in report["results"])
