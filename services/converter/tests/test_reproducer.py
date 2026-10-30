"""Smallest-reproducer evidence in the repair loop (reproducer.py, `run --minimize`).

Doubles in this file are labelled: FakeBreaker and FakeAgent stand in for the two model agents (no model is called),
the minimize/replay doubles return canned records. The integration test at the end uses the REAL verifier, GnuCOBOL
and a JDK, with a fake agent whose "repair" copies the verifier's reference translation over a known-bad Java.
"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

import diocle_converter.__main__ as cli
from diocle_converter.client import ModelClient
from diocle_converter.repair import RepairAgent
from diocle_converter.reproducer import MAX_EVIDENCE_CHARS, Minimizing, evidence_text
from diocle_converter.sources import Program
from diocle_converter.workspace import Workspace
from diocle_verifier.inputs import Case
from test_converter import SAMPLE, ScriptedSDK, report, settings, tool_call

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = json.loads((ROOT / "contracts" / "examples" / "minimal-reproducer.chqclr-nsf-fee.json").read_text())
REFERENCE = ROOT / "services" / "verifier" / "tests" / "fixtures" / "reference"
NAIVE = SAMPLE / "java-conversion"
toolchain = pytest.mark.skipif(not (shutil.which("cobc") and shutil.which("javac")), reason="needs GnuCOBOL and a JDK")


def test_evidence_names_the_fields_that_matter_and_labels_the_opinion():
    text = evidence_text(EXAMPLE)
    assert "RT-FEE=' 1000'" in text and "RT-REASON='NS'" in text
    assert "first difference: output record 1, field CL-FEE" in text
    assert "explanation, not proof" in text and len(text) <= MAX_EVIDENCE_CHARS
    assert "ACCT" not in text.split("fields that matter")[1].split("\n")[0].replace("CQ-ACCT", "")  # neutral fields are left out


def test_availability_follows_the_sandbox_rule(monkeypatch):
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    assert Minimizing.available() is None
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    assert "sandbox" in Minimizing.available()
    monkeypatch.setenv("DIOCLE_IN_SANDBOX", "1")
    assert Minimizing.available() is None


def _double(minimized=True):
    calls = []

    def minimize(sample, java, case_id, contexts, **kw):
        calls.append((case_id, contexts, kw))
        rec = json.loads(json.dumps(EXAMPLE)) | {"id": case_id}
        rec["regression"]["dir"] = f"regression/{case_id}"
        return rec if minimized else {**rec, "status": "not-reproduced", "reason": "passes"}

    return minimize, calls


def test_reduction_caps_and_the_reasons_it_is_skipped(tmp_path):
    minimize, calls = _double()
    events = []
    m = Minimizing(tmp_path, tmp_path, tmp_path, 7, 9.0, 2, events.append, minimize_fn=minimize)
    broken = [{"case": Case(f"b{i}", "model", f"rec{i}"), "why": "tie", "diff": "d"} for i in range(4)]
    out = m.reproduce(broken)
    assert sorted(out) == ["b0", "b1"] and len(calls) == 2  # MINIMIZE_MAX_CASES = 2
    assert calls[0][2]["max_runs"] == 7 and calls[0][2]["max_seconds"] == 9.0
    assert calls[0][2]["explanation"] == {"text": "tie", "source": "breaker"}
    assert (tmp_path / "reproducers" / "b0.json").is_file()


def test_a_failing_reduction_leaves_the_old_evidence_and_never_raises(tmp_path):
    def boom(*a, **k):
        raise RuntimeError("cobc missing")

    events = []
    m = Minimizing(tmp_path, tmp_path, tmp_path, minimize_fn=boom, on_event=events.append)
    assert m.reproduce([{"case": Case("b0", "model", "r"), "why": "", "diff": ""}]) == {}
    assert "skipped: RuntimeError" in events[0]["message"]
    minimize, _ = _double(minimized=False)
    assert Minimizing(tmp_path, tmp_path, tmp_path, minimize_fn=minimize).reproduce(
        [{"case": Case("b0", "model", "r"), "why": "", "diff": ""}]) == {}


class FakeBreaker:  # TEST DOUBLE: breaks the Java once
    def __init__(self, *a, **k):
        self.attempts, self.calls = [], 0

    def attack(self, rounds, label="attack"):
        self.calls += 1
        return [{"case": Case("breaker-attack-r1-01", "model", "REC"), "why": "tie", "diff": "OUT-FEE differs"}] if self.calls == 1 else []


class FakeAgent:  # TEST DOUBLE: records the note it is resumed with
    def __init__(self):
        self.notes = []

    def resume(self, note, extra_rounds):
        self.notes.append(note)
        return {"certified": True, "rounds": [], "certificationReport": None, "lessons": []}


def _attack(monkeypatch, tmp_path, replay_passes):
    monkeypatch.setattr(cli, "Breaker", FakeBreaker)
    (tmp_path / "sample.json").write_text(json.dumps({"layouts": {"input": {}}}))
    program = SimpleNamespace(sample_dir=tmp_path)
    minimize, _ = _double()
    events, agent = [], FakeAgent()
    m = Minimizing(tmp_path, tmp_path, tmp_path, on_event=events.append, minimize_fn=minimize,
                   replay_fn=lambda case_dir, java: {"id": "x", "passed": replay_passes, "detail": "d"})
    outcome, summary = cli._attack(program, None, None, None, agent, [], {"certified": True, "lessons": []}, tmp_path,
                                   settings(), events.append, minimizing=m)
    return outcome, summary, agent, events, m


def test_the_repair_agent_gets_the_minimal_reproducer_not_the_raw_record(monkeypatch, tmp_path):
    outcome, summary, agent, events, m = _attack(monkeypatch, tmp_path, replay_passes=True)
    assert "RT-FEE=' 1000'" in agent.notes[0] and "input='REC'" not in agent.notes[0]
    assert outcome["certified"] and summary["fixed"]
    assert summary["reproducers"] == [{"id": "breaker-attack-r1-01", "status": "minimized", "recordsBefore": 1,
                                       "recordsAfter": 1, "oracleRuns": 15, "afterRepairPassed": True}]
    saved = json.loads((tmp_path / "reproducers" / "breaker-attack-r1-01.json").read_text())
    assert saved["regression"]["afterRepair"]["passed"] is True


def test_a_repair_that_fails_a_saved_regression_case_is_not_certified(monkeypatch, tmp_path):
    outcome, summary, agent, events, m = _attack(monkeypatch, tmp_path, replay_passes=False)
    assert outcome["certified"] is False and not summary["fixed"]
    assert any("still fails 1 saved regression case" in e.get("message", "") for e in events)


def test_without_minimizing_the_note_is_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "Breaker", FakeBreaker)
    (tmp_path / "sample.json").write_text(json.dumps({"layouts": {"input": {}}}))
    agent = FakeAgent()
    cli._attack(SimpleNamespace(sample_dir=tmp_path), None, None, None, agent, [], {"certified": True, "lessons": []},
                tmp_path, settings(), lambda e: None)
    assert "input='REC' (tie): OUT-FEE differs" in agent.notes[0]


def test_a_failed_held_out_certification_hands_the_agent_the_evidence(tmp_path):
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr {}")
    sdk = ScriptedSDK([tool_call("finish", summary="s"), tool_call("finish", summary="s")])
    seen = []

    def evidence(cert, label):
        seen.append(label)
        return "\nSmallest reproducer: ONE RECORD"

    agent = RepairAgent(Program.load(SAMPLE), ws, ModelClient(settings(max_rounds=2), _sdk=sdk), lambda *_: report(False),
                        lambda e: None, evidence=evidence)
    agent.run()
    assert seen == ["r1", "r2"]
    assert "Smallest reproducer: ONE RECORD" in str(sdk.requests[1]["messages"])


def test_held_out_evidence_needs_one_to_one_inputs(tmp_path):
    minimize, calls = _double()
    m = Minimizing(tmp_path, tmp_path, tmp_path, minimize_fn=minimize)
    cert = {"results": [{"inputId": "case-1", "input": "A", "match": True}, {"inputId": "case-2", "input": "B", "match": False}]}
    text = m.certification_evidence(cert, "r1")
    assert "Smallest reproducer" in text and calls[0][1] == [["A", "B"]] and calls[0][2]["hint"] == ["B"]
    assert m.certification_evidence({"results": [{"inputId": "output-0001", "match": False}]}, "r1") == ""


@toolchain
def test_real_loop_reduces_with_the_real_oracle_and_the_repair_passes_the_saved_case(monkeypatch, tmp_path):
    """Breaker double -> REAL reduction against the naive Java -> fake agent 'repairs' by copying the reference Java ->
    REAL replay of the saved regression case against it."""
    from diocle_verifier.verify import verify_sample

    bad = next(r["input"] for r in verify_sample(SAMPLE, random_count=60)["results"] if not r["match"])
    ws = Workspace.from_copy(NAIVE, tmp_path / "run" / "java")
    run_dir = tmp_path / "run"

    class Breaks(FakeBreaker):
        def attack(self, rounds, label="attack"):
            self.calls += 1
            return [{"case": Case("breaker-attack-r1-01", "model", bad), "why": "tie rounding", "diff": "OUT-INTEREST"}] if self.calls == 1 else []

    class Repairs(FakeAgent):
        def resume(self, note, extra_rounds):
            self.notes.append(note)
            for f in ws.root.glob("*.java"):
                f.unlink()
            for f in REFERENCE.glob("IntAccr.java"):
                shutil.copy(f, ws.root / f.name)
            return {"certified": True, "rounds": [], "certificationReport": None, "lessons": []}

    monkeypatch.setattr(cli, "Breaker", Breaks)
    events = []
    m = Minimizing(SAMPLE, ws.root, run_dir, on_event=events.append)
    agent = Repairs()
    outcome, summary = cli._attack(Program.load(SAMPLE), ws, None, None, agent, [], {"certified": True, "lessons": []},
                                   run_dir, settings(), events.append, minimizing=m)
    assert outcome["certified"] and summary["reproducers"][0]["afterRepairPassed"] is True
    assert "fields that matter" in agent.notes[0] and "ACCT-BALANCE" in agent.notes[0]
    saved = json.loads((run_dir / "reproducers" / "breaker-attack-r1-01.json").read_text())
    assert saved["reduction"]["recordsAfter"] == 1 and saved["explanation"]["label"] == "explanation, not proof"
