"""CALL 'CEE3ABD': the translator and the repair agent are told what Diocle's stand-in does (no model calls).

The program is SYNTHETIC, written for this test."""
import json
from pathlib import Path
from types import SimpleNamespace

from diocle_analyzer.analyze import analyze, write_sample
from diocle_converter.prompts import TRANSLATOR, TRANSLATOR_CEE3ABD
from diocle_converter.repair import RepairAgent
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace

SAMPLES = Path(__file__).resolve().parents[3] / "samples"

COBOL = """       IDENTIFICATION DIVISION.
       PROGRAM-ID. ABNDDEMO.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-F ASSIGN TO ABIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-F ASSIGN TO ABOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-F.
       01  IN-REC.
           05  IN-ID    PIC X(4).
       FD  OUT-F.
       01  OUT-REC.
           05  OUT-ID   PIC X(4).
       WORKING-STORAGE SECTION.
       01  WS-EOF       PIC X VALUE 'N'.
       01  ABCODE       PIC S9(9) BINARY.
       01  TIMING       PIC S9(9) BINARY.
       PROCEDURE DIVISION.
           OPEN INPUT IN-F OUTPUT OUT-F
           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-F AT END MOVE 'Y' TO WS-EOF
               NOT AT END
                   IF IN-ID = SPACES
                       PERFORM 9999-ABEND
                   END-IF
                   MOVE IN-ID TO OUT-ID
                   WRITE OUT-REC
               END-READ
           END-PERFORM
           CLOSE IN-F OUT-F
           STOP RUN.
       9999-ABEND.
           MOVE 999 TO ABCODE
           CALL 'CEE3ABD' USING ABCODE, TIMING.
"""


class RecordingClient:
    """Test double for the model client: records the prompt, answers with a stub Java (never run)."""

    def __init__(self):
        self.messages = None
        self.settings = SimpleNamespace(max_rounds=0)

    def chat(self, **kwargs):
        self.messages = kwargs["messages"]
        content = json.dumps({"mainClass": "Abnddemo", "javaSource": "class Abnddemo {}", "notes": "test double"})
        return SimpleNamespace(message=SimpleNamespace(content=content))


def _sample(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "ABNDDEMO.cbl").write_text(COBOL)
    report = analyze(repo)
    [p] = report["programs"]
    assert p["convertible"] and p["standIns"] == ["CEE3ABD"], p["notConvertibleReason"]
    return write_sample(repo, report, p, tmp_path / "samples")


def test_translator_is_told_what_the_stand_in_does(tmp_path):
    program = Program.load(_sample(tmp_path))
    assert program.stand_ins == ("CEE3ABD",)
    client = RecordingClient()
    translate(program, client, Workspace(tmp_path / "ws"))
    system = client.messages[0]["content"]
    assert system.endswith(TRANSLATOR_CEE3ABD)
    assert "System.exit(16)" in system and "CEE3ABD abend code <n>" in system and "not IBM's" in system
    assert "stderr is not" in system and "close every file" in system


def test_repair_agent_is_told_too(tmp_path):
    program = Program.load(_sample(tmp_path))
    ws = Workspace(tmp_path / "ws")
    ws.write("Abnddemo.java", "class Abnddemo {}")
    report = {"runs": {"original": {"compiled": True, "exitCode": 16, "stdout": "", "stderr": ""},
                       "converted": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                       "stdoutMatch": True, "exitCodeMatch": False},
              "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}
    agent = RepairAgent(program, ws, RecordingClient(), lambda *a: report)
    agent.run()
    assert "System.exit(16)" in agent.messages[1]["content"]


def test_programs_without_cee3abd_are_told_nothing_about_it(tmp_path):
    program = Program.load(SAMPLES / "display-report")
    assert program.stand_ins == () and program.stand_in_text() == ""
    client = RecordingClient()
    translate(program, client, Workspace(tmp_path / "ws"))
    assert client.messages[0]["content"] == TRANSLATOR.format(io=program.io_text(), main_class=program.main_class)
    assert "CEE3ABD" not in client.messages[0]["content"]
