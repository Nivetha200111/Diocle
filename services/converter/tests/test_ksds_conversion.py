"""Keyed-file programs: what the translator and the repair agent are told (no model calls; the verifier is the judge)."""
import json
from pathlib import Path

from diocle_converter.prompts import REPAIR, TRANSLATOR, TRANSLATOR_KSDS, TRANSLATOR_SQL
from diocle_converter.repair import summarize_report
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace

SAMPLES = Path(__file__).resolve().parents[3] / "samples"
SAMPLE = SAMPLES / "vsam-customer-update"


class RecordingClient:
    """Test double for the model client: records the prompt, answers with the fixture Java."""

    def __init__(self, java):
        self.java, self.messages = java, None

    def chat(self, **kwargs):
        self.messages = kwargs["messages"]
        content = json.dumps({"mainClass": "Custupd", "javaSource": self.java, "notes": "test double"})
        return type("C", (), {"message": type("M", (), {"content": content})()})()


def test_keyed_program_gets_the_file_description_the_support_class_and_the_contract(tmp_path):
    program = Program.load(SAMPLE)
    assert program.ksds and program.keyed[0]["recordLength"] == 38
    io = program.io_text()
    assert "CUSTMAST is a KEYED (INDEXED) file" in io and "38-byte records" in io and "byte offset 2 length 6" in io
    assert "DD_CUSTMAST" not in io.split("KEYED")[0]  # the keyed file is not offered as a plain DD path
    assert "public final class DioKsds" in program.support_text() and "DioKsds" not in program.as_text()  # the guard reads as_text()
    client = RecordingClient((SAMPLE / "java-conversion/Custupd.java").read_text())
    translate(program, client, Workspace(tmp_path / "ws"))
    system = client.messages[0]["content"]
    assert "public final class DioKsds" in client.messages[1]["content"]
    assert system.endswith(TRANSLATOR_KSDS) and "DioKsds.select" in system and "'23'" in system and "'46'" in system
    assert "unsigned bytes" in system and "never compare keys with EBCDIC" in system


def test_other_programs_are_told_nothing_about_keyed_files(tmp_path):
    for name in ("display-report", "db2-account-report"):
        program = Program.load(SAMPLES / name)
        client = RecordingClient("class X {}")
        translate(program, client, Workspace(tmp_path / name))
        system = client.messages[0]["content"]
        assert "DioKsds" not in system and "DioKsds" not in client.messages[1]["content"]
        assert system == TRANSLATOR.format(io=program.io_text(), main_class=program.main_class) + (TRANSLATOR_SQL if program.sql else "")


def test_keyed_file_diff_reaches_the_repair_agent_as_evidence():
    report = {"runs": {"original": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                       "converted": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                       "stdoutMatch": True, "exitCodeMatch": True},
              "results": [{"program": "P", "inputId": "keyed:CUSTMAST", "inputSource": "keyed", "outputDd": "keyed:CUSTMAST",
                           "match": False, "fieldDiffs": [{"field": "CUSTMAST[K00001]", "original": "AAK00001...C", "converted": "AAK00001...N"}],
                           "diff": "keyed file CUSTMAST (key CM-CUST-ID): position 4 key 'K00001' value: original 'AAK00001...C' converted 'AAK00001...N'; records: original 9 converted 9 (seeded 8)",
                           "originalOutput": "AAK00001...C", "convertedOutput": "AAK00001...N"}],
              "summary": {"total": 1, "passed": 0, "failed": 1}}
    text = summarize_report(report)
    assert "keyed file CUSTMAST" in text and "original record:" in text and "AAK00001...N" in text
    assert "keyed" in REPAIR and "DioKsds.java" in REPAIR


def test_workspace_compiles_with_the_verifiers_own_support_class(tmp_path):
    ws = Workspace.from_copy(SAMPLE / "java-conversion", tmp_path / "ws")
    ok, output = ws.compile()
    assert ok, output
    ws.write("Custupd.java", ws.read("Custupd.java").replace("cust.open(", "cust.nonexistent("))
    ok, output = ws.compile()
    assert not ok and "nonexistent" in output


def test_verifier_sentences_reach_the_run_record_without_a_class_name():
    from diocle_converter.__main__ import _describe
    from diocle_verifier.runners import ProgramTimeout, VerifierUnavailable

    assert _describe(ProgramTimeout("original", ["x"], 120)) == (
        "the original program did not terminate within 120 seconds, so there is nothing to compare against")
    assert _describe(VerifierUnavailable("the SQLite JDBC driver is not installed on the verifier")).startswith("the SQLite JDBC")
    assert _describe(ValueError("x")) == "ValueError: x"
