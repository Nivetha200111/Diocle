"""The WRITE ... ADVANCING rule reaches the prompts only of programs that use it (no model calls).

The earlier measurements describe the prompts pinned here: a program without it must get them unchanged, byte for byte.
GnuCOBOL's real bytes are checked against the rule in services/verifier/tests/test_write_advancing.py. Programs here are SYNTHETIC."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from diocle_converter.prompts import REPAIR, REPAIR_ADVANCING, TRANSLATOR, TRANSLATOR_ADVANCING
from diocle_converter.repair import RepairAgent
from diocle_converter.sources import Program, _writes_advancing
from diocle_converter.translate import translation_messages
from diocle_converter.workspace import Workspace

REPO = Path(__file__).resolve().parents[3]
ALL_SAMPLES = sorted(p.parent for base in (REPO / "samples", REPO / "eval" / "samples") for p in base.glob("*/sample.json")
                     if "javaConversion" in json.loads(p.read_text()))  # jobs have none


def line(text: str) -> str:
    return " " * 11 + text + "\n"


@pytest.mark.parametrize("code", [
    "WRITE R AFTER ADVANCING 1 LINES.",
    "WRITE R BEFORE ADVANCING PAGE.",
    "WRITE R AFTER 2 LINES.",
    "WRITE R BEFORE 1.",
    "write r after advancing 1 line.",
    "WRITE R FROM W AFTER 1.",
    "WRITE R FROM W OF G (I) BEFORE 1.",
    "WRITE R FROM 'AB' AFTER 1.",
])
def test_every_form_of_it_is_found(code):
    assert _writes_advancing(line(code))


def test_it_is_found_across_lines_in_a_copybook_style_paragraph():
    assert _writes_advancing(line("WRITE PRINT-REC") + line("    AFTER ADVANCING 1 LINES."))


@pytest.mark.parametrize("source", [
    line("DISPLAY 'X' WITH NO ADVANCING."),
    line("DISPLAY 'X' NO ADVANCING."),
    line("DISPLAY 'X' WITH NO") + line("    ADVANCING."),
    line("WRITE R."),
    line("WRITE R") + line("PERFORM P WITH TEST AFTER UNTIL X = 1."),
    line("REWRITE R AFTER."),
    line("MOVE 'WRITE R AFTER ADVANCING 1 LINE' TO W."),
    line("MOVE ADVANCING-COUNT TO W."),
    "      * WRITE R AFTER ADVANCING 1 LINE.\n",
    "      / WRITE R AFTER ADVANCING 1 LINE.\n",
    line("MOVE 1 TO W. *> WRITE R AFTER ADVANCING 1 LINE."),
    line("MOVE 1 TO W.".ljust(61) + "ADVANCING"),  # past column 72: not code in fixed format
])
def test_nothing_else_turns_it_on(source):
    assert not _writes_advancing(source)


def test_free_format_is_read_as_free_format():
    assert _writes_advancing(">>SOURCE FORMAT FREE\nWRITE R AFTER ADVANCING 1 LINE.\n")
    assert not _writes_advancing(">>SOURCE FORMAT FREE\n*> WRITE R AFTER ADVANCING 1 LINE.\n")
    assert _writes_advancing(">>SOURCE FORMAT FREE\n" + " " * 70 + "WRITE R AFTER ADVANCING 1 LINE.\n")  # no column 72


def _report() -> dict:
    return {"runs": {"original": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                     "converted": {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""},
                     "stdoutMatch": True, "exitCodeMatch": True},
            "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}


def _repair_system(program: Program, tmp_path: Path) -> str:
    ws = Workspace(tmp_path / "ws")
    ws.write(f"{program.main_class}.java", "class X {}")
    agent = RepairAgent(program, ws, SimpleNamespace(settings=SimpleNamespace(max_rounds=0)), lambda *a: _report())
    agent.run()
    return agent.messages[0]["content"]


def _with_advancing(tmp_path: Path, where: str = "source") -> Program:
    sample = tmp_path / "sample"
    (sample / "src").mkdir(parents=True)
    (sample / "copybooks").mkdir()
    clause = "           WRITE OUT-REC AFTER ADVANCING 1 LINE.\n"
    (sample / "src" / "ADV.cbl").write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. ADV.\n" + (clause if where == "source" else ""))
    (sample / "copybooks" / "PARA.cpy").write_text(clause if where == "copybook" else "       01  X PIC X.\n")
    if where == "module":
        (sample / "src" / "SUB.cbl").write_text(clause)
    (sample / "sample.json").write_text(json.dumps({
        "program": "ADV", "source": "src/ADV.cbl", "modules": ["src/SUB.cbl"] if where == "module" else [], "copybookDir": "copybooks",
        "dd": {"input": "I", "output": "O"}, "javaConversion": {"dir": "java", "mainClass": "Adv"}}))
    return Program.load(sample)


@pytest.mark.parametrize("where", ["source", "copybook", "module"])
def test_a_program_that_uses_it_is_told_in_both_prompts(tmp_path, where):
    program = _with_advancing(tmp_path, where)
    assert program.uses_advancing()
    assert translation_messages(program)[0]["content"] == TRANSLATOR.format(io=program.io_text(), main_class=program.main_class) + TRANSLATOR_ADVANCING
    assert _repair_system(program, tmp_path) == REPAIR + REPAIR_ADVANCING


def test_the_rule_says_what_the_failures_showed_was_missing():
    for text in (TRANSLATOR_ADVANCING, REPAIR_ADVANCING):
        assert "if the flag is true, write one 0x0A" in text and "SEQUENTIAL file too" in text and "0x0C" in text and "0x0D" in text
    assert "short last piece is only wrong if its bytes differ" in REPAIR_ADVANCING and "no probe or debug line" in REPAIR_ADVANCING
    assert "probe" not in TRANSLATOR_ADVANCING


def test_the_convert_anyway_prompt_is_never_told(tmp_path):
    program = _with_advancing(tmp_path)
    assert TRANSLATOR_ADVANCING not in translation_messages(program, anyway_reason="nothing compares it")[0]["content"]


def test_no_sample_in_this_repository_uses_it_so_every_prompt_is_unchanged(tmp_path):
    """The pin: for all of them, the system prompts are exactly the constants the earlier measurements ran with."""
    assert len(ALL_SAMPLES) > 10
    for i, sample in enumerate(ALL_SAMPLES):
        program = Program.load(sample)
        assert not program.uses_advancing(), program.name
        system = translation_messages(program)[0]["content"]
        assert TRANSLATOR_ADVANCING not in system and "0x0C" not in system, program.name
        assert program.advancing_text(REPAIR_ADVANCING) == ""
        assert _repair_system(program, tmp_path / str(i)) == REPAIR, program.name


def test_the_base_prompts_themselves_did_not_move():
    """Hashes of TRANSLATOR and REPAIR before this rule was added (commit 001e8b5). A change to them is a change to what the
    earlier measurements describe, so it must be made deliberately, here."""
    assert hashlib.sha256(TRANSLATOR.encode()).hexdigest() == "768b68640129da74bd36a520290893012e6303f0edf0dd7001286cd328896178"
    assert hashlib.sha256(REPAIR.encode()).hexdigest() == "c1a4d2458f5caccd2895615b0328e774b122393d00392079001eb1620f4e5881"
