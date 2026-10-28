"""Unit tests with a scripted stand-in for the model API (no network, no credits).

The scripted SDK below is a TEST DOUBLE: it replays fixed responses so the agent loop,
caps and safety rules can be tested deterministically. It is never used outside tests.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from diocle_converter.client import BudgetExceeded, ModelClient
from diocle_converter.config import Settings
from diocle_converter.memory import MAX_LESSONS, Memory, render
from diocle_converter.repair import CERT_SEED, TEST_SEED, RepairAgent, summarize_report
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "interest-accrual"


def settings(**overrides):
    base = dict(mode="hosted", base_url="http://unused", api_key="test", model="muse-spark-1.3-contributor",
                reasoning_effort="low", max_calls_per_run=10, max_calls_per_round=5, max_rounds=2)
    return Settings(**{**base, **overrides})


class ScriptedSDK:
    def __init__(self, messages):
        self.script = list(messages)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = self.script.pop(0)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=200,
                                prompt_tokens_details=SimpleNamespace(cached_tokens=800),
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=50))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def tool_call(name, **args):
    return ChatCompletionMessage(role="assistant", content=None, tool_calls=[
        {"id": f"call-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}])


def report(passed: bool):
    runs = {side: {"compiled": True, "exitCode": 0, "stdout": "x", "stderr": ""} for side in ("original", "converted")}
    result = {"program": "P", "inputId": "case-1", "match": passed, "fieldDiffs": [] if passed else
              [{"field": "OUT-FEE", "original": "1.49", "converted": "1.50"}], "diff": "" if passed else "OUT-FEE differs"}
    return {"version": "0.2", "results": [result], "summary": {"total": 1, "passed": int(passed), "failed": int(not passed)},
            "runs": {**runs, "stdoutMatch": True}}


def test_workspace_confines_reads_and_writes(tmp_path):
    ws = Workspace(tmp_path / "java")
    ws.write("A.java", "class A { int x = 1; }")
    for bad in ("../escape.java", "/etc/passwd", "notes.txt"):
        with pytest.raises(PermissionError):
            ws.read(bad)
    result = ws.patch("A.java", "x = 1", "x = 2")
    assert result.startswith("applied") and "int x = 2" in result  # excerpt spares the agent a re-read
    assert "rejected" in ws.patch("A.java", "missing", "y")
    assert ws.compile()[0]


def test_client_enforces_call_cap_and_logs_usage():
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content="ok")] * 3)
    client = ModelClient(settings(max_calls_per_run=2), _sdk=sdk)
    client.chat(role="t", round=0, messages=[])
    client.chat(role="t", round=0, messages=[])
    with pytest.raises(BudgetExceeded):
        client.chat(role="t", round=0, messages=[])
    usage = client.usage_summary()
    assert usage["calls"] == 2 and usage["inputTokens"] == 2000 and usage["cachedInputTokens"] == 1600
    assert usage["estimatedCostUsd"] == pytest.approx((400 * 0.10 + 1600 * 0.002 + 400 * 0.20) / 1e6, abs=1e-6)
    assert sdk.requests[0]["reasoning_effort"] == "low"


def test_agent_patches_then_certification_uses_held_out_seed(tmp_path):
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr { String fee = \"round\"; }")
    seeds = []

    def verify(java_dir, seed, random_count):
        seeds.append(seed)
        return report("truncate" in (java_dir / "IntAccr.java").read_text())

    sdk = ScriptedSDK([
        tool_call("run_differential_test"),
        tool_call("patch_java", path="IntAccr.java", old_text="\"round\"", new_text="\"truncate\"",
                  rationale="COMPUTE without ROUNDED truncates"),
        tool_call("compile_java"),
        tool_call("finish", summary="fee truncation"),
    ])
    events = []
    agent = RepairAgent(Program.load(SAMPLE), ws, ModelClient(settings(), _sdk=sdk), verify, events.append)
    outcome = agent.run()

    assert outcome["certified"]
    assert seeds[0] == TEST_SEED and seeds[-1] == CERT_SEED + 1  # certification inputs differ from what the agent saw
    steps = [e for e in events if e["type"] == "agent-step"]
    assert [e["tool"] for e in steps] == ["run_differential_test", "patch_java", "compile_java", "finish"]
    assert steps[1]["rationale"] == "COMPUTE without ROUNDED truncates"
    messages = sdk.requests[-1]["messages"]
    call_ids = [c["id"] for m in messages if m["role"] == "assistant" for c in m.get("tool_calls", [])]
    assert call_ids == [m["tool_call_id"] for m in messages if m["role"] == "tool"]  # every tool call got its reply
    assert "PROCEDURE DIVISION" in messages[1]["content"] and "class IntAccr" in messages[1]["content"]  # context up front


def test_agent_stops_at_round_cap_without_certifying(tmp_path):
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr {}")
    sdk = ScriptedSDK([tool_call("finish", summary="gave up")] * 2)
    agent = RepairAgent(Program.load(SAMPLE), ws, ModelClient(settings(), _sdk=sdk), lambda *_: report(False))
    outcome = agent.run()
    assert not outcome["certified"] and len(outcome["rounds"]) == 2


def test_tool_errors_are_returned_to_the_model(tmp_path):
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr {}")
    sdk = ScriptedSDK([tool_call("read_java_file", path="../../secrets.java"), tool_call("finish", summary="x")])
    events = []
    RepairAgent(Program.load(SAMPLE), ws, ModelClient(settings(max_rounds=1), _sdk=sdk), lambda *_: report(False), events.append).run()
    assert events[0]["resultSummary"].startswith("error:") and "outside the Java workspace" in events[0]["resultSummary"]


def test_passing_result_tells_the_agent_to_stop():
    assert "Call finish now" in summarize_report(report(True))
    assert "Call finish now" not in summarize_report(report(False))
    assert "Call finish now" not in summarize_report(report(True), for_agent=False)  # certification text for people


def test_translator_is_pinned_to_the_class_the_verifier_runs(tmp_path):
    answer = json.dumps({"mainClass": "IntAccr", "javaSource": "public class IntAccr {}", "notes": "n"})
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=answer)])
    ws = Workspace(tmp_path / "java")
    result = translate(Program.load(SAMPLE), ModelClient(settings(), _sdk=sdk), ws)
    request = sdk.requests[0]
    assert "must be named IntAccr" in request["messages"][0]["content"]
    schema = request["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["mainClass"]["enum"] == ["IntAccr"]
    assert result["file"] == "IntAccr.java" and ws.read("IntAccr.java") == "public class IntAccr {}"


LESSON = {"pattern": "COMPUTE ROUNDED ties", "cobol": "rounds half away from zero", "java": "BigDecimal HALF_UP"}


def test_memory_keeps_clean_deduplicated_capped_lessons(tmp_path):
    memory = Memory(tmp_path / "memory.json")
    assert memory.learn([LESSON, {"pattern": "", "cobol": "x", "java": "y"}, "junk"], program="P", run_id="r1") == 1
    updated = {**LESSON, "pattern": "Compute ROUNDED: ties!", "java": "setScale(2, HALF_UP)"}
    assert memory.learn([updated], program="Q", run_id="r2") == 0  # same pattern: replaced, not duplicated
    assert [(m["java"], m["run"]) for m in memory.load()] == [("setScale(2, HALF_UP)", "r2")]
    for i in range(MAX_LESSONS + 5):
        memory.learn([{**LESSON, "pattern": f"pattern {i}"}], program="P", run_id=f"r{i}")
    assert len(memory.load()) == MAX_LESSONS
    assert render([]) == "" and "hints only" in render(memory.load())


def test_lessons_count_only_when_certified_and_hints_reach_the_model(tmp_path):
    for certifies in (True, False):
        ws = Workspace(tmp_path / f"java-{certifies}")
        ws.write("IntAccr.java", "class IntAccr {}")
        sdk = ScriptedSDK([tool_call("finish", summary="s", lessons=[LESSON])] * 2)
        agent = RepairAgent(Program.load(SAMPLE), ws, ModelClient(settings(), _sdk=sdk), lambda *_: report(certifies),
                            hints=render([LESSON]))
        outcome = agent.run()
        assert outcome["lessons"] == ([LESSON] if certifies else [])
        first = sdk.requests[0]["messages"][1]["content"]
        assert first.startswith("Lessons from earlier certified repairs") and "BigDecimal HALF_UP" in first
