"""EXEC SQL programs: what the translator and the repair agent are told (no model calls; the verifier is the judge)."""
import json
import shutil
from pathlib import Path

import pytest

from diocle_converter.prompts import REPAIR, TRANSLATOR, TRANSLATOR_SQL
from diocle_converter.repair import summarize_report
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace

SAMPLES = Path(__file__).resolve().parents[3] / "samples"


class RecordingClient:
    """Test double for the model client: records the prompt, answers with the fixture Java."""

    def __init__(self, java):
        self.java, self.messages = java, None

    def chat(self, **kwargs):
        self.messages = kwargs["messages"]
        content = json.dumps({"mainClass": "Acctrpt", "javaSource": self.java, "notes": "test double"})
        return type("C", (), {"message": type("M", (), {"content": content})()})()


def test_sql_program_gets_the_tables_the_support_class_and_the_contract(tmp_path):
    program = Program.load(SAMPLES / "db2-account-report")
    assert program.sql and "TABLE ACCOUNTS: ACCT_ID CHAR(8) NOT NULL" in program.as_text()
    assert "DECIMAL(9,2) (stored x 10^2)" in program.as_text()
    assert "public final class DioSql" in program.support_text() and "DioSql" not in program.as_text()  # the guard reads as_text()
    assert "final contents of its tables are compared" in program.io_text()
    client = RecordingClient((SAMPLES / "db2-account-report/java-conversion/Acctrpt.java").read_text())
    translate(program, client, Workspace(tmp_path / "ws"))
    system = client.messages[0]["content"]
    assert "public final class DioSql" in client.messages[1]["content"]
    assert system.endswith(TRANSLATOR_SQL) and "DioSql.connect()" in system and "-811" in system and "+100" in system
    assert "never" in system.lower() and "setAutoCommit" in system  # the rules the guard and verifier rely on


def test_other_programs_are_told_nothing_about_sql(tmp_path):
    program = Program.load(SAMPLES / "display-report")
    client = RecordingClient("class X {}")
    translate(program, client, Workspace(tmp_path / "ws"))
    assert "DioSql" not in client.messages[0]["content"] and client.messages[0]["content"] == TRANSLATOR.format(
        io=program.io_text(), main_class=program.main_class)


def test_table_diff_reaches_the_repair_agent_as_evidence():
    report = {"runs": {"original": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                       "converted": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                       "stdoutMatch": True, "exitCodeMatch": True},
              "results": [{"program": "P", "inputId": "table:AUDIT", "inputSource": "database", "outputDd": "table:AUDIT",
                           "match": False, "fieldDiffs": [{"field": "AUDIT.NEW_BAL", "original": "1.00", "converted": "1.01"}],
                           "diff": "table AUDIT (columns A, B): row 3 column NEW_BAL: original '1.00' converted '1.01'; rows: original 5 converted 5 (seeded 0)",
                           "originalOutput": "3,K1,0.00,1.00", "convertedOutput": "3,K1,0.00,1.01"}],
              "summary": {"total": 1, "passed": 0, "failed": 1}}
    text = summarize_report(report)
    assert "table AUDIT" in text and "AUDIT.NEW_BAL" in text and "original rows:" in text and "3,K1,0.00,1.01" in text
    assert "table" in REPAIR and "DioSql.java" in REPAIR


def test_workspace_compiles_with_the_verifiers_own_support_class(tmp_path):
    ws = Workspace.from_copy(SAMPLES / "db2-account-report/java-conversion", tmp_path / "ws")
    ok, output = ws.compile()
    assert ok, output
    ws.write("Acctrpt.java", ws.read("Acctrpt.java").replace("DioSql.connect()", "DioSql.nonexistent()"))
    ok, output = ws.compile()
    assert not ok and "nonexistent" in output
