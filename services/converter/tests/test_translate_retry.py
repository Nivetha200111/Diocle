"""The translator's one retry on an unusable answer, seen in real runs: Muse Spark Open on Baseten sometimes ran to the host's
32,768-token limit, nearly all blank lines, so its JSON was cut off.

AnswersSDK below is a TEST DOUBLE: it replays fixed answers (no network, no credits) and is never used outside tests.
"""

import ast
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai import APIError

import diocle_converter.__main__ as cli
from diocle_converter.client import BudgetExceeded, ModelClient
from diocle_converter.config import Settings
from diocle_converter.sources import Program
from diocle_converter.translate import TranslationUnusable, translate
from diocle_converter.workspace import Workspace

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "interest-accrual"
GOOD = json.dumps({"mainClass": "IntAccr", "javaSource": "public class IntAccr {}", "notes": "n"})
CUT_OFF = ('{"mainClass": "IntAccr", "javaSource": "public class IntAccr {' + "\\n" * 500, "length")  # (text, finish_reason)
FULL_OUTPUT = 32_768  # the host's limit: what a cut-off answer really bills
OPEN_MODEL = "meta-models/muse-spark-open-1026"


def settings(**overrides):
    base = dict(mode="private", base_url="http://unused", api_key="test", model=OPEN_MODEL,
                reasoning_effort="low", max_calls_per_run=10, max_calls_per_round=5, max_rounds=2)
    return Settings(**{**base, **overrides})


class AnswersSDK:
    """TEST DOUBLE: each item is an answer's text, or (text, finish_reason). Every call bills `output` tokens."""

    def __init__(self, answers, output=200):
        self.answers, self.output, self.requests = list(answers), output, []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        answer = self.answers.pop(0)
        text, reason = answer if isinstance(answer, tuple) else (answer, "stop")
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=self.output, prompt_tokens_details=None,
                                completion_tokens_details=None)
        return SimpleNamespace(usage=usage, choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason=reason)])


def attempt(tmp_path, sdk, retry=True, **overrides):
    """Returns (client, workspace, events, a function that runs translate())."""
    client, ws, events = ModelClient(settings(**overrides), _sdk=sdk), Workspace(tmp_path / "java"), []
    return client, ws, events, lambda: translate(Program.load(SAMPLE), client, ws, retry=retry, on_event=events.append)


def no_java(ws):
    return not list(ws.root.glob("*.java"))


def test_a_cut_off_answer_then_a_good_one_succeeds_and_both_calls_count(tmp_path):
    sdk = AnswersSDK([CUT_OFF, GOOD], output=FULL_OUTPUT)
    client, ws, events, run = attempt(tmp_path, sdk)
    assert run()["file"] == "IntAccr.java" and ws.read("IntAccr.java") == "public class IntAccr {}"
    usage = client.usage_summary()
    assert usage["calls"] == 2 and usage["outputTokens"] == 2 * FULL_OUTPUT
    assert usage["estimatedCostUsd"] == pytest.approx(2 * (1000 * 1.25 + FULL_OUTPUT * 4.25) / 1e6, abs=1e-6)
    assert [c.role for c in client.calls] == ["translator", "translator"]
    assert sdk.requests[0]["messages"] == sdk.requests[1]["messages"]  # the same translation again
    assert "max_tokens" not in sdk.requests[0] and "max_tokens" not in sdk.requests[1]
    [event] = events
    assert event["type"] == "stage" and event["stage"] == "translating"
    assert "cut off" in event["message"] and "once more" in event["message"]


@pytest.mark.parametrize("bad", [
    '{"mainClass": "IntAccr", "javaSource": "class',  # cut off by a host that reports no finish_reason
    None,  # no text at all
    "[]",
    json.dumps({"mainClass": "IntAccr", "javaSource": "public class IntAccr {}"}),  # a required field missing
    json.dumps({"mainClass": "IntAccr", "javaSource": "\n\n\n", "notes": "n"}),  # blank lines, not Java
    json.dumps({"mainClass": "IntAccr", "javaSource": 7, "notes": "n"}),
    json.dumps({"mainClass": "", "javaSource": "public class IntAccr {}", "notes": "n"}),
])
def test_any_unusable_answer_gets_the_retry(tmp_path, bad):
    client, ws, _, run = attempt(tmp_path, AnswersSDK([bad, GOOD]))
    run()
    assert len(client.calls) == 2 and ws.read("IntAccr.java") == "public class IntAccr {}"


def test_a_length_answer_is_retried_even_if_its_text_parses(tmp_path):
    client, _, _, run = attempt(tmp_path, AnswersSDK([(GOOD, "length"), GOOD]))
    run()
    assert len(client.calls) == 2


def test_two_bad_answers_give_the_plain_failure_and_no_third_call(tmp_path):
    sdk = AnswersSDK([CUT_OFF, "{not json", GOOD])
    client, ws, events, run = attempt(tmp_path, sdk)
    with pytest.raises(TranslationUnusable) as caught:
        run()
    message = str(caught.value)
    assert message == ("The model's answer was cut off at the host's output limit, and the one retry was cut off or unreadable, "
                       "so no Java was produced.")
    assert "not json" not in message and "Expecting" not in message  # no parser text, no model text
    assert len(sdk.requests) == 2 and client.usage_summary()["calls"] == 2 and len(events) == 1 and no_java(ws)


def test_the_dollar_cap_blocking_the_retry_gives_the_plain_failure(tmp_path):
    # A real cut-off answer costs about $0.14; the cap projects another as dear, and 2 x 0.14 does not fit under $0.20.
    sdk = AnswersSDK([CUT_OFF, GOOD], output=FULL_OUTPUT)
    client, ws, _, run = attempt(tmp_path, sdk, max_usd=0.20)
    with pytest.raises(TranslationUnusable, match="call or spend cap left no room.*no Java was produced") as caught:
        run()
    assert isinstance(caught.value.__cause__, BudgetExceeded)
    assert len(sdk.requests) == 1 and client.usage_summary()["calls"] == 1 and no_java(ws)


def test_the_same_dollar_cap_allows_the_retry_when_it_fits(tmp_path):
    client, ws, _, run = attempt(tmp_path, AnswersSDK([CUT_OFF, GOOD], output=FULL_OUTPUT), max_usd=0.30)
    run()
    assert len(client.calls) == 2 and ws.read("IntAccr.java")


def test_a_cap_refusing_the_first_call_stays_a_budget_refusal(tmp_path):
    sdk = AnswersSDK([GOOD])
    _, _, _, run = attempt(tmp_path, sdk, max_calls_per_run=0)
    with pytest.raises(BudgetExceeded):
        run()
    assert not sdk.requests


def test_one_call_allowed_means_no_retry_and_a_failure_the_evals_count_as_before(tmp_path):
    # distill_glimmer.first_try's client (max_calls_per_run=1), even with retry on.
    sdk = AnswersSDK([CUT_OFF, GOOD])
    client, ws, _, run = attempt(tmp_path, sdk, max_calls_per_run=1)
    with pytest.raises(TranslationUnusable, match="no Java was produced") as caught:
        run()
    assert len(sdk.requests) == 1 and len(client.calls) == 1 and no_java(ws)
    # What first_try's `except` branches need: not a host error (distill re-raises APIError, headline re-runs infrastructure
    # errors), not a cap refusal (distill's teach() would gate it "spend-cap"). So translated=False, passed=False, as before.
    assert not isinstance(caught.value, (APIError, BudgetExceeded)) and getattr(caught.value, "status_code", None) is None


def test_the_default_never_retries_however_many_calls_are_allowed(tmp_path):
    # eval/headline.py's first_try: ModelClient(Settings.from_env()), 60 calls by default, so the cap alone would not stop a retry.
    sdk = AnswersSDK([CUT_OFF, GOOD])
    client, ws, _, _ = attempt(tmp_path, sdk, max_calls_per_run=60)
    with pytest.raises(TranslationUnusable, match="^The model's answer was cut off at the host's output limit, so no Java was produced"):
        translate(Program.load(SAMPLE), client, ws)
    assert len(sdk.requests) == 1


@pytest.mark.parametrize("script", ["headline.py", "distill_glimmer.py"])
def test_the_first_try_measurements_do_not_ask_for_the_retry(script):
    calls = [n for n in ast.walk(ast.parse((ROOT / "eval" / script).read_text()))
             if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "translate"]
    assert calls and all("retry" not in {k.arg for k in c.keywords} for c in calls)


def test_a_stored_answer_without_a_finish_reason_still_reads(tmp_path):
    """The shape of eval/distill_glimmer.py's StoredAnswer: a choice with only a message."""
    class Stored:
        def chat(self, **_):
            return SimpleNamespace(message=SimpleNamespace(content=GOOD))

    ws = Workspace(tmp_path / "java")
    assert translate(Program.load(SAMPLE), Stored(), ws)["mainClass"] == "IntAccr"


def run_cli(tmp_path, monkeypatch, sdk, *flags):
    sample = tmp_path / "samples" / "s"
    shutil.copytree(SAMPLE, sample)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings()))
    monkeypatch.setattr(cli.Settings, "guard_from_env", classmethod(lambda cls: None))
    monkeypatch.setattr(cli, "ModelClient", lambda s: ModelClient(s, _sdk=sdk))
    with pytest.raises(TranslationUnusable):
        cli.main(["run", str(sample), "--no-memory", *flags])
    [run_json] = (tmp_path / "runs").glob("*/run.json")
    events = [json.loads(line) for line in (run_json.parent / "events.jsonl").read_text().splitlines()]
    return json.loads(run_json.read_text()), events, run_json.parent


def test_a_run_records_the_retry_and_the_plain_failure(tmp_path, monkeypatch):
    run, events, run_dir = run_cli(tmp_path, monkeypatch, AnswersSDK([CUT_OFF, CUT_OFF], output=FULL_OUTPUT))
    sentence = ("The model's answer was cut off at the host's output limit, and the one retry was cut off at the host's output "
                "limit, so no Java was produced.")
    assert run["status"] == "not-certified" and run["certified"] is False and run["error"] == sentence
    assert run["usage"]["calls"] == 2 and run["usage"]["outputTokens"] == 2 * FULL_OUTPUT
    assert run["usage"]["estimatedCostUsd"] == pytest.approx(2 * (1000 * 1.25 + FULL_OUTPUT * 4.25) / 1e6, abs=1e-6)
    assert any("trying once more" in e.get("message", "") for e in events)
    assert events[-1]["message"] == f"run failed: {sentence}"
    assert "JSONDecodeError" not in json.dumps(run) and not list((run_dir / "java").glob("*.java"))


def test_a_run_whose_dollar_cap_blocks_the_retry_records_the_plain_failure(tmp_path, monkeypatch):
    sdk = AnswersSDK([CUT_OFF, GOOD], output=FULL_OUTPUT)
    run, events, _ = run_cli(tmp_path, monkeypatch, sdk, "--max-usd", "0.20")
    assert "call or spend cap left no room" in run["error"] and "no Java was produced" in run["error"]
    assert run["usage"]["calls"] == 1 and len(sdk.requests) == 1


def test_convert_anyway_publishes_the_same_sentence():
    assert cli.describe_exception(TranslationUnusable("The model's answer was unreadable, so no Java was produced.")) \
        == "The model's answer was unreadable, so no Java was produced."
