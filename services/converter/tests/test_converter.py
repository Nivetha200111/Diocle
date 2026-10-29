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
            "runs": {**runs, "stdoutMatch": True, "exitCodeMatch": True}}


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


def test_skill_export_has_frontmatter_and_provenance():
    from diocle_converter.skill import render_skill
    text = render_skill([{**LESSON, "program": "INTACCR", "run": "interest-accrual-1"}])
    assert text.startswith("---\nname: cobol-to-java-semantics\ndescription: ")
    assert "### COMPUTE ROUNDED ties" in text and "run `interest-accrual-1`" in text
    assert "_No certified lessons yet._" in render_skill([])


def test_breaker_rejects_cases_that_do_not_fit_the_layout():
    from diocle_converter.breaker import to_record
    from diocle_verifier.layout import load_fields
    fields = load_fields(json.loads((SAMPLE / "sample.json").read_text())["layouts"]["input"])
    good = {"ACCT-ID": "TIE", "ACCT-BALANCE": "-36.50", "ACCT-RATE": "0.0500", "ACCT-DAYS": "1", "ACCT-TIER": "S"}
    assert to_record(fields, good) == "TIE       -0000000365000500001S"
    assert to_record(fields, {**good, "ACCT-BALANCE": "1.234"}) is None  # more decimals than the PIC holds
    assert to_record(fields, {**good, "ACCT-DAYS": "1000"}) is None  # too many digits
    assert to_record(fields, {**good, "ACCT-RATE": "-0.05"}) is None  # unsigned field
    assert to_record(fields, {k: v for k, v in good.items() if k != "ACCT-TIER"}) is None
    for bad in ("NaN", "Infinity", "-inf", "sNaN"):
        assert to_record(fields, {**good, "ACCT-BALANCE": bad}) is None
    assert to_record(fields, {**good, "ACCT-ID": "A\nB"}) is None and to_record(fields, {**good, "ACCT-ID": "Ä"}) is None
    assert to_record(fields, {**good, "ACCT-DAYS": 5}) is None  # not a string


def test_breaker_attacks_until_an_input_breaks_the_java(tmp_path):
    from diocle_converter.breaker import Breaker
    layout = json.loads((SAMPLE / "sample.json").read_text())["layouts"]["input"]
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr {}")
    case = lambda bal: {"fields": [{"name": "ACCT-ID", "value": "X"}, {"name": "ACCT-BALANCE", "value": bal},
                                   {"name": "ACCT-RATE", "value": "0.0500"}, {"name": "ACCT-DAYS", "value": "1"},
                                   {"name": "ACCT-TIER", "value": "S"}], "why": "tie"}
    junk = {"cases": [case("36.50"), "not-a-case", {"fields": "nope"}, {"fields": [{"name": "ACCT-ID"}]}]}
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=json.dumps(junk)),
                       ChatCompletionMessage(role="assistant", content=json.dumps({"cases": [case("-36.50"), case("1.234")]}))])

    def verify(java_dir, seed, random_count, extra_cases):
        results = [{"inputId": c.id, "inputSource": c.source, "input": c.record, "match": "-" not in c.record[10:11],
                    "diff": "OUT-INTEREST differs"} for c in extra_cases]
        return {"results": results}

    events = []
    broken = Breaker(Program.load(SAMPLE), ws, ModelClient(settings(), _sdk=sdk), verify, layout, events.append).attack(rounds=3)
    assert [b["case"].record for b in broken] == ["X         -0000000365000500001S"]
    assert [e["broke"] for e in events] == [0, 1] and "1 rejected" in events[1]["message"]
    assert len(sdk.requests) == 2  # stopped at the first breaking round


def test_swarm_agent_receives_lessons_certified_by_others_mid_run(tmp_path):
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr {}")
    shared = []
    sdk = ScriptedSDK([tool_call("compile_java"), tool_call("finish", summary="s")])

    def feed():
        if sdk.requests:  # another agent certifies after our first call
            shared[:] = [{**LESSON, "program": "FEESCHD"}]
        return shared

    events = []
    agent = RepairAgent(Program.load(SAMPLE), ws, ModelClient(settings(max_rounds=1), _sdk=sdk), lambda *_: report(True),
                        events.append, memory_feed=feed)
    agent.run()
    assert [e["message"] for e in events if e["type"] == "memory"] == ["Received 1 new lesson(s) from FEESCHD mid-run"]
    messages = sdk.requests[1]["messages"]  # the live conversation
    update = next(i for i, m in enumerate(messages) if "Shared memory update" in str(m.get("content")))
    assert messages[update - 1]["role"] == "tool" and messages[update + 1]["role"] == "assistant"  # between two calls


def test_certification_is_revoked_if_the_breaker_still_breaks_the_java(tmp_path, monkeypatch):
    import diocle_converter.__main__ as cli
    from diocle_verifier.inputs import Case

    class FakeBreaker:
        def __init__(self, *a, **k):
            self.attempts = [{"id": "breaker-attack-r1-01"}]

        def attack(self, rounds, label="attack"):  # breaks every time, even after the repair
            return [{"case": Case(f"b-{label}", "model", "X"), "why": "tie", "diff": "OUT differs"}]

    class FakeAgent:
        def resume(self, note, extra_rounds):
            return {"certified": True, "rounds": [], "certificationReport": None, "lessons": [LESSON]}

    monkeypatch.setattr(cli, "Breaker", FakeBreaker)
    (tmp_path / "sample.json").write_text(json.dumps({"layouts": {"input": {}}}))
    program = SimpleNamespace(sample_dir=tmp_path)
    standing, events = [], []
    outcome, summary = cli._attack(program, None, None, None, FakeAgent(), standing,
                                   {"certified": True, "lessons": [LESSON]}, tmp_path, settings(), events.append)
    assert outcome["certified"] is False and outcome["lessons"] == []  # nothing learned from an unproven run
    assert summary["repairCycles"] == 1 and summary["broke"] == 2 and not summary["fixed"]
    assert len(standing) == 2 and (tmp_path / "breaker.json").exists()


def test_a_crashed_run_is_marked_not_certified(tmp_path, monkeypatch):
    import shutil
    import diocle_converter.__main__ as cli
    shutil.copytree(SAMPLE, tmp_path / "samples" / "s")
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings()))

    def boom(*a, **k):
        raise RuntimeError("translator exploded")

    monkeypatch.setattr(cli, "_convert", boom)
    with pytest.raises(RuntimeError):
        cli.main(["run", str(tmp_path / "samples" / "s")])
    [run_json] = (tmp_path / "runs").glob("*/run.json")
    run = json.loads(run_json.read_text())
    assert run["status"] == "not-certified" and "translator exploded" in run["error"]
    last = json.loads((run_json.parent / "events.jsonl").read_text().splitlines()[-1])
    assert last["message"].startswith("run failed: RuntimeError")


def test_translator_is_told_every_file_of_a_multi_file_program(tmp_path):
    answer = json.dumps({"mainClass": "Acctmtch", "javaSource": "public class Acctmtch {}", "notes": "n"})
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=answer)])
    translate(Program.load(SAMPLE.parent / "account-match"), ModelClient(settings(), _sdk=sdk), Workspace(tmp_path / "j"))
    system = sdk.requests[0]["messages"][0]["content"]
    assert "DD_MSTIN, DD_TXNIN" in system and "DD_NEWMST, DD_EXCOUT" in system


# Real jobs[] entry for samples/account-match/jcl/QMKD010.jcl (services/analyzer's analyze() output,
# copied verbatim -- see test_pipeline.py's JOB for how to reproduce it).
JOB_FIXTURE = {
    "name": "QMKD010", "member": "jcl/QMKD010.jcl",
    "steps": [
        {"step": "SORT005", "proc": None, "kind": "sort", "program": "SORT",
         "dds": {"SORTIN": "QMK.PROD.TXN.DAILY", "SORTOUT": "QMK.PROD.TXN.SORTED",
                 "SYSIN": "QMK.PROD.CNTLLIB(SORTTXN)"},
         "sort": {"fields": [[1, 8, "CH", "A"]], "optionEquals": True, "unsupported": None},
         "convertibleProgram": None, "notConvertibleReason": None},
        {"step": "MTCH010", "proc": None, "kind": "cobol", "program": "ACCTMTCH",
         "dds": {"MSTIN": "QMK.PROD.ACCT.MASTER(0)", "TXNIN": "QMK.PROD.TXN.SORTED",
                 "NEWMST": "QMK.PROD.ACCT.MASTER(+1)", "EXCOUT": "QMK.PROD.TXN.EXCEPTIONS(+1)"},
         "sort": None, "convertibleProgram": True, "notConvertibleReason": None},
    ],
    "wiring": [{"fromStep": "SORT005", "fromDd": "SORTOUT", "toStep": "MTCH010", "toDd": "TXNIN",
                "dsn": "QMK.PROD.TXN.SORTED"}],
    "convertible": True, "notConvertibleReason": None,
}


def test_run_job_translates_once_and_writes_a_job_pipelines_manifest(tmp_path, monkeypatch):
    """run-job: one model call for the COBOL step (translate.py, unchanged), zero model calls for the SORT
    step (sortgen.py), reusing the account-match sample as-is (jcl/SORTIN.txt, sample.json's fixtureFiles
    seed MSTIN since no jcl/MSTIN.txt exists)."""
    import diocle_converter.__main__ as cli

    monkeypatch.setattr(cli, "_analyzer_jobs", lambda sample_dir: [JOB_FIXTURE])
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)

    java_source = (SAMPLE.parent / "account-match" / "java-conversion" / "Acctmtch.java").read_text()
    answer = json.dumps({"mainClass": "Acctmtch", "javaSource": java_source, "notes": "n"})
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=answer)])
    client = ModelClient(settings(), _sdk=sdk)

    rc = cli._run_job(SAMPLE.parent / "account-match", settings(), client)
    assert rc == 0
    assert len(sdk.requests) == 1  # exactly one model call: the COBOL step only

    [run_dir] = tmp_path.glob("runs/account-match-job-*")
    manifest = json.loads((run_dir / "job-pipeline.json").read_text())
    [pipeline] = manifest["jobPipelines"]
    assert pipeline["job"] == "QMKD010" and pipeline["driverClass"] == "Qmkd010Driver"
    steps = {s["step"]: s for s in pipeline["steps"]}
    assert steps["SORT005"]["origin"] == "deterministic"
    assert steps["MTCH010"]["origin"] == "model" and steps["MTCH010"]["mainClass"] == "Acctmtch"
    assert manifest["usage"]["calls"] == 1
    assert (run_dir / "job" / "Qmkd010Driver.java").exists()
    assert (run_dir / "job" / f"{steps['SORT005']['mainClass']}.java").exists()


def test_run_job_rejects_a_sample_whose_program_does_not_match_the_jobs_cobol_step(tmp_path, monkeypatch):
    import diocle_converter.__main__ as cli

    monkeypatch.setattr(cli, "_analyzer_jobs", lambda sample_dir: [JOB_FIXTURE])
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    with pytest.raises(SystemExit, match="ACCTMTCH"):
        cli._run_job(SAMPLE, settings(), ModelClient(settings(), _sdk=ScriptedSDK([])))  # SAMPLE is interest-accrual


def _env(monkeypatch, **values):
    import diocle_converter.config as config
    monkeypatch.setattr(config, "load_dotenv", lambda *a, **k: None)
    for name in ("CROSSCHECK_MODEL_API_KEY", "CROSSCHECK_MODEL_BASE_URL", "CROSSCHECK_MODEL_ID",
                 "OPEN_MODEL_API_KEY", "OPEN_MODEL_BASE_URL", "OPEN_MODEL_ID", "CROSSCHECK_MAX_CALLS"):
        monkeypatch.delenv(name, raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def test_crosscheck_settings_use_the_open_model_with_their_own_cap(monkeypatch):
    _env(monkeypatch)
    assert settings().for_crosscheck() is None  # nothing configured
    _env(monkeypatch, OPEN_MODEL_API_KEY="k", OPEN_MODEL_BASE_URL="https://host/v1", OPEN_MODEL_ID="meta-models/muse-spark-open-1026")
    cross = settings().for_crosscheck()
    assert (cross.mode, cross.model, cross.base_url, cross.max_calls_per_run) == ("private", "meta-models/muse-spark-open-1026", "https://host/v1", 2)
    assert cross.api_key == "k" and settings().api_key != "k"  # the main run's key is untouched
    _env(monkeypatch, OPEN_MODEL_API_KEY="k", OPEN_MODEL_BASE_URL="u", OPEN_MODEL_ID="m", CROSSCHECK_MODEL_ID="other", CROSSCHECK_MAX_CALLS="1")
    assert settings().for_crosscheck().model == "other" and settings().for_crosscheck().max_calls_per_run == 1
    private = Settings(**{**settings().__dict__, "mode": "private"})
    assert private.for_crosscheck() is None  # an open-model run cannot independently check itself


def test_usage_prices_each_call_by_its_own_model():
    spark = ModelClient(settings(), _sdk=ScriptedSDK([ChatCompletionMessage(role="assistant", content="ok")]))
    spark.chat(role="translator", round=0, messages=[])
    open_settings = Settings(**{**settings().__dict__, "mode": "private", "model": "accounts/fireworks/models/muse-spark-open"})
    opened = ModelClient(open_settings, _sdk=ScriptedSDK([ChatCompletionMessage(role="assistant", content="ok")]))
    opened.chat(role="crosscheck", round=1, messages=[])
    spark.calls.extend(opened.calls)
    expected = (200 * 0.10 + 800 * 0.002 + 200 * 0.20 + 200 * 1.25 + 800 * 0.15 + 200 * 4.25) / 1e6
    assert spark.usage_summary()["estimatedCostUsd"] == pytest.approx(expected, abs=1e-6)
    assert [c["role"] for c in spark.usage_summary()["modelCalls"]] == ["translator", "crosscheck"]


def test_crosscheck_runs_its_cases_and_the_models_opinion_never_certifies(tmp_path):
    from diocle_converter.crosscheck import make_crosschecker, summarize
    layout = json.loads((SAMPLE / "sample.json").read_text())["layouts"]["input"]
    ws = Workspace(tmp_path / "java")
    ws.write("IntAccr.java", "class IntAccr {}")
    case = lambda bal, why: {"fields": [{"name": "ACCT-ID", "value": "X"}, {"name": "ACCT-BALANCE", "value": bal},
                                        {"name": "ACCT-RATE", "value": "0.0500"}, {"name": "ACCT-DAYS", "value": "1"},
                                        {"name": "ACCT-TIER", "value": "S"}], "why": why}
    answer = {"cases": [case("-36.50", "negative tie"), case("1.234", "too many decimals"), case("0.00", "zero")],
              "suspected": [{"field": "ACCT-BALANCE", "concern": "Java may round negative ties toward zero"}, "junk"]}
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=json.dumps(answer))])
    seen = []

    def verify(java_dir, seed, random_count, extra_cases):
        seen.extend(extra_cases)
        return {"results": [{"inputId": c.id, "inputSource": c.source, "input": c.record, "match": "-" not in c.record[10:11],
                             "diff": "OUT-INTEREST differs"} for c in extra_cases]}

    events = []
    checker = make_crosschecker(Program.load(SAMPLE), ws, ModelClient(settings(), _sdk=sdk), verify, layout, events.append)
    broken = checker.attack(rounds=1, label="crosscheck")
    # only the case that really differs on GnuCOBOL vs Java counts; "suspected" is recorded but is only an opinion
    assert [b["case"].record for b in broken] == ["X         -0000000365000500001S"]
    assert len(seen) == 2 and all(c.source == "model" for c in seen)  # the invalid case never reached the verifier
    assert checker.client.calls[0].role == "crosscheck" and sdk.requests[0]["response_format"]["json_schema"]["name"] == "crosscheck"
    assert events[0]["type"] == "crosscheck" and events[0]["message"].startswith("Cross-check round 1")
    summary = summarize(checker, "m", {"broke": 1, "repairCycles": 0, "fixed": False,
                                       "counterexamples": [{"input": "X", "why": "w", "diff": "d"}]})
    assert (summary["casesProposed"], summary["casesValid"], summary["mismatches"]) == (3, 2, 1)
    assert summary["suspected"] == [{"field": "ACCT-BALANCE", "concern": "Java may round negative ties toward zero"}]


def test_crosscheck_is_skipped_when_unconfigured_and_never_breaks_a_certified_run(monkeypatch, tmp_path):
    import diocle_converter.__main__ as cli
    _env(monkeypatch)
    (tmp_path / "sample.json").write_text(json.dumps({"layouts": {"input": {}}}))
    program = SimpleNamespace(sample_dir=tmp_path)
    certified = {"certified": True, "lessons": [LESSON]}
    events = []
    outcome, result = cli._crosscheck(program, None, None, None, None, [], certified, tmp_path, settings(), events.append)
    assert outcome is certified and result["skipped"].startswith("no CROSSCHECK_MODEL_*")
    assert events[0]["message"].startswith("Cross-check skipped")

    _env(monkeypatch, OPEN_MODEL_API_KEY="k", OPEN_MODEL_BASE_URL="u", OPEN_MODEL_ID="m")

    def host_down(*a, **k):
        raise RuntimeError("503")

    monkeypatch.setattr(cli, "_attack", host_down)
    monkeypatch.setattr(cli, "ModelClient", lambda s: SimpleNamespace(calls=[]))
    client = SimpleNamespace(calls=[])
    outcome, result = cli._crosscheck(program, None, client, None, None, [], certified, tmp_path, settings(), events.append)
    assert outcome["certified"] is True and result["skipped"] == "unavailable: RuntimeError"


def test_a_bad_crosscheck_setting_skips_instead_of_crashing_a_certified_run(monkeypatch, tmp_path):
    import diocle_converter.__main__ as cli
    _env(monkeypatch, OPEN_MODEL_API_KEY="k", OPEN_MODEL_BASE_URL="u", OPEN_MODEL_ID="m", CROSSCHECK_MAX_CALLS="abc")
    certified = {"certified": True, "lessons": []}
    outcome, result = cli._crosscheck(SimpleNamespace(sample_dir=tmp_path), None, None, None, None, [], certified,
                                      tmp_path, settings(), lambda e: None)
    assert outcome is certified and result == {"skipped": "invalid CROSSCHECK_* setting"}


def test_an_original_that_does_not_compile_stops_the_run_before_any_repair_round():
    from diocle_converter.__main__ import original_failure
    broken = {"runs": {"original": {"compiled": False, "exitCode": 1, "stdout": "", "stderr":
              "/tmp/job/CBL0001.cobol:10: error: syntax error, unexpected ENVIRONMENT\n    10 >        ENVIRONMENT DIVISION.\n"},
              "converted": {"compiled": True}}}
    why = original_failure(broken)
    assert "does not compile under GnuCOBOL" in why and "unexpected ENVIRONMENT" in why and "cannot be verified" in why
    assert original_failure({"runs": {"original": {"compiled": True}, "converted": {"compiled": False}}}) is None  # Java errors are repairable
    assert original_failure(None) is None and original_failure({}) is None
