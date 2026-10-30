"""Convert-anyway: COBOL repair, labels, caps. The model is the ScriptedSDK TEST DOUBLE from test_converter (no network)."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

import diocle_converter.__main__ as cli
from diocle_converter import anyway
from diocle_converter.client import BudgetExceeded, ModelClient
from diocle_converter.cobolrepair import (Limits, changed_lines, check_patch, deterministic_fixes, make_patched_sample,
                                          repair_original)
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace

from test_converter import ScriptedSDK, settings, tool_call

REPO = Path(__file__).resolve().parents[3] / "samples" / "convert-anyway-repo"
needs_cobc = pytest.mark.skipif(shutil.which("cobc") is None, reason="GnuCOBOL not installed")


def make_sample(tmp_path, program: str, anyway_meta=None) -> Path:
    s = tmp_path / program.lower()
    (s / "src").mkdir(parents=True)
    shutil.copytree(REPO / "copybooks", s / "copybooks")
    shutil.copy(REPO / "cobol" / f"{program}.cbl", s / "src" / f"{program}.cbl")
    meta = {"name": program.lower(), "program": program, "source": f"src/{program}.cbl", "copybookDir": "copybooks",
            "javaConversion": {"dir": "j", "mainClass": program.capitalize()}, "dd": {"input": "ACCTIN", "output": "ACCTOUT"}}
    if anyway_meta:
        meta = {k: v for k, v in meta.items() if k != "dd"} | {"convertAnyway": anyway_meta}
    (s / "sample.json").write_text(json.dumps(meta))
    return s


def cobc_check(sample: Path):
    from diocle_verifier.precheck import compile_local

    answer = compile_local(sample)
    return answer.status, answer.diagnostics


def client_for(*messages, **overrides):
    return ModelClient(settings(**overrides), _sdk=ScriptedSDK(list(messages)))


# ---- deterministic fix -------------------------------------------------------------------------

def test_deterministic_fix_adds_only_the_missing_period():
    text = (REPO / "cobol" / "NOPERIOD.cbl").read_text()
    fixed, fixes = deterministic_fixes(text)
    assert len(fixes) == 1 and "PROGRAM-ID NOPERIOD" in fixes[0]
    assert changed_lines(text, fixed) == 1
    assert [l for l in fixed.split("\n") if "PROGRAM-ID" in l] == ["       PROGRAM-ID. NOPERIOD."]
    ok = (REPO / "cobol" / "ADDFEE.cbl").read_text()
    assert deterministic_fixes(ok) == (ok, [])  # nothing to fix: unchanged


@needs_cobc
def test_deterministic_repair_is_free_never_overwrites_and_labels_the_patch(tmp_path):
    sample = make_sample(tmp_path, "NOPERIOD")
    original = (sample / "src" / "NOPERIOD.cbl").read_text()
    client = client_for()  # no scripted answers: any model call would crash
    patched, record, reason = repair_original(sample, client, escalate=False, on_event=lambda e: None,
                                              compile_check=cobc_check)
    assert reason is None and patched is not None and client.calls == []
    assert record["method"] == "deterministic" and record["outcome"] == "compiles" and record["changedLines"] == 1
    assert record["modelCalls"] == 0 and "+       PROGRAM-ID. NOPERIOD." in record["diff"]
    assert (sample / "src" / "NOPERIOD.cbl").read_text() == original  # the user's file is untouched
    assert (sample / "src" / "NOPERIOD.repaired.cbl").exists() and (patched / "src" / "NOPERIOD.repaired.cbl").exists()
    assert json.loads((patched / "sample.json").read_text())["source"] == "src/NOPERIOD.repaired.cbl"
    assert cobc_check(patched)[0] == "ok"


def test_a_program_that_compiles_or_is_unknown_is_left_alone(tmp_path):
    sample = make_sample(tmp_path, "ADDFEE")
    for status in ("ok", "unknown"):
        assert repair_original(sample, client_for(), escalate=False, on_event=lambda e: None,
                               compile_check=lambda s, st=status: (st, [])) == (None, None, None)
    assert not list(tmp_path.glob("*.repaired"))


# ---- model repair (scripted) --------------------------------------------------------------------

@needs_cobc
def test_model_repair_fixes_only_the_reported_line(tmp_path):
    sample = make_sample(tmp_path, "BADNAME")
    original = (sample / "src" / "BADNAME.cbl").read_text()
    client = client_for(tool_call("patch_cobol", old_text="MOVE 50 TO WS-FEES", new_text="MOVE 50 TO WS-FEE",
                                  rationale="undefined name"),
                        tool_call("compile_cobol"), tool_call("finish", ok=True, summary="typo"))
    patched, record, reason = repair_original(sample, client, escalate=False, on_event=lambda e: None,
                                              compile_check=cobc_check)
    assert reason is None and record["method"] == "model" and record["outcome"] == "compiles"
    assert record["changedLines"] == 1 and record["modelCalls"] == 3 and record["estimatedCostUsd"] > 0
    assert "WS-FEES" in record["diff"] and "undefined" in record["fixes"][0]
    assert (sample / "src" / "BADNAME.cbl").read_text() == original
    assert "WS-FEES" not in (patched / "src" / "BADNAME.repaired.cbl").read_text()


ORIG = (REPO / "cobol" / "BADNAME.cbl").read_text()
LIM = Limits(max_lines=20, max_share=0.10)


def edit(old, new, text=ORIG):
    assert old in text
    return text.replace(old, new, 1)


def rejected(candidate, diag=(37,), previous=ORIG):
    why = check_patch(previous, candidate, ORIG, list(diag), LIM)
    assert why and why.startswith("rejected"), why
    return why


def test_legitimate_fixes_are_accepted():
    assert check_patch(ORIG, edit("WS-FEES", "WS-FEE"), ORIG, [37], LIM) is None  # identifier typo on the reported line
    noperiod = (REPO / "cobol" / "NOPERIOD.cbl").read_text()
    fixed = edit("PROGRAM-ID. NOPERIOD", "PROGRAM-ID. NOPERIOD.", noperiod)
    assert check_patch(noperiod, fixed, noperiod, [5], LIM) is None  # the period goes on the line before the reported one


def test_deleting_or_neutralising_the_failing_statement_is_rejected():
    lines = ORIG.split("\n")
    assert "add or remove lines" in rejected("\n".join(lines[:36] + lines[37:]))  # the statement is gone
    assert "blanks" in rejected(edit("               MOVE 50 TO WS-FEES", "                                    "))
    assert "token" in rejected(edit("MOVE 50 TO WS-FEES", "CONTINUE        "))  # replaced by a no-op
    assert "token" in rejected(edit("MOVE 50 TO WS-FEES", "MOVE 0 TO WS-FEE"))  # logic rewritten on the reported line
    assert "not an identifier" in rejected(edit("MOVE 50 TO WS-FEES", "MOVE 99 TO WS-FEES"))  # a literal changed


def test_edits_away_from_the_reported_line_are_rejected_in_every_division():
    assert "not a line the compiler reported" in rejected(edit("WS-FEE                      PIC 9(3)V99", "WS-FEE                      PIC 9(9)V99"))
    assert "not a line the compiler reported" in rejected(edit("VALUE 'N'", "VALUE 'Y'"))  # DATA DIVISION VALUE
    assert "not a line the compiler reported" in rejected(edit("COPY ACCTIN", "COPY ACCTOT"))  # a COPY
    assert "not a line the compiler reported" in rejected(edit("ORGANIZATION IS LINE SEQUENTIAL.\n           SELECT ACCT-OUT",
                                                              "ORGANIZATION IS SEQUENTIAL.\n           SELECT ACCT-OUT"))
    # real logic next to the diagnostic (inside the old +/-2 window) is not the reported line either
    assert "not a line the compiler reported" in rejected(edit("AI-AMOUNT * 0.025", "AI-AMOUNT * 0.001"))
    assert "not a line the compiler reported" in rejected(edit("IF WS-FEE > 50", "IF WS-FEE > 5000"))
    # even ON a reported line, a PIC or VALUE change is not an allowed kind of edit
    why = rejected(edit("PIC 9(3)V99", "PIC 9(9)V99"), diag=(21,))
    assert "not an identifier" in why or "not a single" in why


def test_edits_split_across_patches_cannot_drift():
    first = edit("WS-FEES", "WS-FEEX")
    assert check_patch(ORIG, first, ORIG, [37], LIM) is None
    # a second patch on the same (still reported) line, judged against the ORIGINAL line, cannot walk away from it
    assert "edit distance" in rejected(edit("WS-FEEX", "WS-TOTALS", first), previous=first)
    # a patch on another line is refused because it was not reported
    assert "not a line the compiler reported" in rejected(edit("IF WS-FEE > 50", "IF WS-FEE > 500", first), previous=first)


def test_line_count_changes_are_rejected_so_diagnostics_cannot_go_stale():
    assert "add or remove lines" in rejected(edit("           MOVE AI-ACCT-ID TO AO-ACCT-ID", "           MOVE 1 TO WS-FEE\n           MOVE AI-ACCT-ID TO AO-ACCT-ID"))


def test_free_format_tab_and_headerless_files_fail_closed():
    free = ">>SOURCE FORMAT FREE\n" + ORIG
    tabbed = ORIG.replace("       0000-MAIN.", "\t0000-MAIN.")
    for text in (free, tabbed):
        why = check_patch(text, text.replace("WS-FEES", "WS-FEE"), text, [38], LIM)
        assert why and "only fixed-format files" in why
    no_proc = ORIG.replace("PROCEDURE DIVISION", "PROCEDURE  DIVIS")
    assert "PROCEDURE DIVISION" in check_patch(no_proc, edit("WS-FEES", "WS-FEE", no_proc), no_proc, [37], LIM)
    misaligned = "\n".join(l[1:] if l.startswith("       ") else l for l in ORIG.split("\n"))  # code shifted a column left
    assert check_patch(misaligned, misaligned.replace("WS-FEES", "WS-FEE"), misaligned, [37], LIM)


def test_size_limit_still_applies():
    many = ORIG.replace("AO-", "AQ-").replace("AI-", "AJ-").replace("WS-", "WT-")  # each line is an allowed identifier edit; together they are too many
    assert changed_lines(ORIG, many) > 4
    assert "differ from the original by" in check_patch(ORIG, many, ORIG, list(range(1, 60)), LIM)


@needs_cobc
def test_agent_demands_a_compile_after_every_patch(tmp_path):
    sample = make_sample(tmp_path, "BADNAME")
    client = client_for(
        tool_call("patch_cobol", old_text="MOVE 50 TO WS-FEES", new_text="MOVE 50 TO WS-FEEX", rationale="a"),
        tool_call("patch_cobol", old_text="WS-FEEX", new_text="WS-FEE", rationale="b"),  # no compile in between
        tool_call("finish", ok=False, summary="x"))
    events = []
    repair_original(sample, client, escalate=False, on_event=events.append, compile_check=cobc_check)
    steps = [e["resultSummary"] for e in events if e.get("tool") == "patch_cobol"]
    assert steps[0].startswith("applied") and "compile_cobol first" in steps[1]


def test_limits_are_clamped(monkeypatch):
    monkeypatch.setenv("COBOL_REPAIR_MAX_LINES", "100000")
    monkeypatch.setenv("COBOL_REPAIR_MAX_SHARE", "0.99")
    monkeypatch.setenv("COBOL_REPAIR_MAX_CALLS", "500")
    got = Limits.from_env()
    assert (got.max_lines, got.max_share, got.max_calls) == (50, 0.25, 20)


def test_crlf_files_keep_their_line_endings():
    text = (REPO / "cobol" / "NOPERIOD.cbl").read_text().replace("\n", "\r\n")
    fixed, fixes = deterministic_fixes(text)
    assert len(fixes) == 1 and "PROGRAM-ID. NOPERIOD.\r\n" in fixed and fixed.count("\r\n") == text.count("\r\n")


@needs_cobc
def test_model_patch_over_the_limit_is_rejected_and_the_file_unchanged(tmp_path):
    sample = make_sample(tmp_path, "BADNAME")
    big_new = "\n".join(f"           DISPLAY 'LINE {i}'" for i in range(30))
    client = client_for(tool_call("patch_cobol", old_text="           MOVE 50 TO WS-FEES", new_text=big_new, rationale="x"),
                        tool_call("finish", ok=False, summary="gave up"))
    patched, record, reason = repair_original(sample, client, escalate=False, on_event=lambda e: None,
                                              compile_check=cobc_check)
    assert patched is None and record["outcome"] == "still-fails" and "could not make it compile" in reason
    assert record["changedLines"] == 0  # the rejected patch was never applied
    assert not (tmp_path / "badname.repaired").exists() and not (sample / "src" / "BADNAME.repaired.cbl").exists()


@needs_cobc
def test_model_repair_cap_reached(tmp_path, monkeypatch):
    monkeypatch.setenv("COBOL_REPAIR_MAX_CALLS", "2")
    sample = make_sample(tmp_path, "BADNAME")
    client = client_for(tool_call("read_cobol"), tool_call("compile_cobol"), tool_call("read_cobol"))
    patched, record, reason = repair_original(sample, client, escalate=False, on_event=lambda e: None,
                                              compile_check=cobc_check)
    assert patched is None and record["outcome"] == "cap-reached" and len(client.calls) == 2


def test_model_may_not_claim_success_the_compiler_decides(tmp_path):
    sample = make_sample(tmp_path, "BADNAME")
    client = client_for(tool_call("finish", ok=True, summary="done"))
    patched, record, reason = repair_original(sample, client, escalate=False, on_event=lambda e: None,
                                              compile_check=lambda s: ("fail", ["BADNAME.cbl:37: error: ... is not defined"]))
    assert patched is None and record["outcome"] == "still-fails"


# ---- labels, caps, prompts ---------------------------------------------------------------------

def test_assurance_labels_and_wording():
    repair = {"changedLines": 2}
    got = cli._assurance_fields({"certified": True, "rounds": []}, True, repair, None)
    assert got["assurance"] == anyway.REPAIRED and "not the original" in got["assuranceReason"]
    assert "A person must confirm" in got["assuranceReason"]
    assert cli._assurance_fields({"certified": True, "rounds": []}, False, None, None)["assurance"] == anyway.CERTIFIED
    failed = cli._assurance_fields({"certified": False, "rounds": [{"summary": {"passed": 3, "total": 5}}]}, False, None, None)
    assert failed["assurance"] == anyway.FAILED and "3/5" in failed["assuranceReason"]
    assert "certified" not in anyway.unverified_wording("x").lower().replace("could not run", "")
    assert anyway.LABELS == ("certified", "certified-against-repaired-cobol", "compiled-unverified", "failed")


def test_dollar_cap_stops_the_next_call():
    client = client_for(ChatCompletionMessage(role="assistant", content="a"), ChatCompletionMessage(role="assistant", content="b"),
                        max_usd=0.0000001)
    client.chat(role="t", round=0, messages=[])  # first call is allowed: nothing spent yet
    with pytest.raises(BudgetExceeded, match="spend cap"):
        client.chat(role="t", round=0, messages=[])


def test_enabled_by_flag_or_env(monkeypatch):
    monkeypatch.delenv("DIOCLE_CONVERT_ANYWAY", raising=False)
    assert not anyway.enabled(False) and anyway.enabled(True)
    monkeypatch.setenv("DIOCLE_CONVERT_ANYWAY", "1")
    assert anyway.enabled(False)


def test_anyway_prompt_names_the_reason_the_adapters_and_the_missing_copybooks(tmp_path):
    sample = make_sample(tmp_path, "ADDFEE", {"reason": "EXEC SQL needs a database adapter", "missingCopybooks": ["GONE"]})
    program = Program.load(sample)
    assert program.anyway and program.files == []
    answer = json.dumps({"mainClass": "Addfee", "javaSource": "public class Addfee {}", "notes": "n"})
    client = client_for(ChatCompletionMessage(role="assistant", content=answer))
    translate(program, client, Workspace(tmp_path / "j"))
    system, user = client.settings and client._sdk.requests[0]["messages"]
    assert "EXEC SQL needs a database adapter" in system["content"] and "ADAPTER REQUIRED" in system["content"]
    assert "never fake" in system["content"].lower() or "Never fake" in system["content"]
    assert "GONE" in user["content"]


@pytest.mark.skipif(shutil.which("javac") is None, reason="JDK not installed")
def test_compile_fix_rounds_then_unverified_record_never_runs_java(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    ws = Workspace(tmp_path / "runs" / "r1" / "java")
    ws.write("Addfee.java", "public class Addfee { int x = ; }")
    good = json.dumps({"javaSource": "public class Addfee { int x = 1; }"})
    client = client_for(ChatCompletionMessage(role="assistant", content=good))
    run_dir = tmp_path / "runs" / "r1"
    events = []
    guard = SimpleNamespace(client=None, summary=lambda: {"policy": "n/a"})
    program = SimpleNamespace(main_class="Addfee")
    code = cli._finish_unverified(settings(), client, program, run_dir, {"program": "ADDFEE", "command": "run", "sample": "s"},
                                  events, events.append, guard, {"mainClass": "Addfee"}, ws,
                                  "EXEC SQL needs a database adapter", None)
    run = json.loads((run_dir / "run.json").read_text())
    assert code == 3 and run["assurance"] == "compiled-unverified" and run["certified"] is False
    assert run["status"] == "not-certified" and "EXEC SQL" in run["assuranceReason"]
    assert run["usage"]["calls"] == 1 and "NEVER RUN" in (run_dir / "PROVENANCE.md").read_text()


@pytest.mark.skipif(shutil.which("javac") is None, reason="JDK not installed")
def test_unfixable_java_is_failed_within_the_fix_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    ws = Workspace(tmp_path / "runs" / "r2" / "java")
    ws.write("Addfee.java", "public class Addfee { int x = ; }")
    bad = json.dumps({"javaSource": "public class Addfee { int y = ; }"})
    client = client_for(*[ChatCompletionMessage(role="assistant", content=bad)] * 5)
    guard = SimpleNamespace(client=None, summary=lambda: {})
    code = cli._finish_unverified(settings(), client, SimpleNamespace(main_class="Addfee"), tmp_path / "runs" / "r2",
                                  {"program": "ADDFEE", "command": "run", "sample": "s"}, [], lambda e: None, guard, None, ws,
                                  "no output", None)
    run = json.loads((tmp_path / "runs" / "r2" / "run.json").read_text())
    assert code == 1 and run["assurance"] == "failed" and run["certified"] is False
    assert len(client.calls) == anyway.COMPILE_FIX_ROUNDS  # bounded
