"""The paid evaluation path of eval/distill_glimmer.py against a labelled fake host. Nothing here reaches Fireworks."""

import importlib.util
import json
import os
import sys
import time
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from diocle_converter import distill

ROOT = Path(__file__).resolve().parents[3]
ACCOUNT = "someone-at-example-9x"


@pytest.fixture
def dg(tmp_path, monkeypatch):
    """The runner, imported with the environment restored afterwards: it sets its own settings at import."""
    saved = dict(os.environ)
    spec = importlib.util.spec_from_file_location("distill_glimmer_under_test", ROOT / "eval" / "distill_glimmer.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "DIR", tmp_path)
    monkeypatch.setattr(module, "OUT", tmp_path / "results.json")
    monkeypatch.setattr(module, "HARVEST", tmp_path / "harvest.json")
    monkeypatch.setattr(module, "K", 1)
    monkeypatch.setattr(module, "answers", lambda model, settings: True)
    for key, value in (("OPEN_MODEL_API_KEY", "k"), ("OPEN_MODEL_BASE_URL", "http://fake.invalid"), ("OPEN_MODEL_ID", "accounts/fireworks/models/muse-spark-open")):
        monkeypatch.setenv(key, value)
    (tmp_path / "training.json").write_text(json.dumps({"status": "completed"}))
    yield module
    distill._ACCOUNTS.clear()
    os.environ.clear()
    os.environ.update(saved)
    sys.modules.pop(spec.name, None)


class FakeHost(distill.Fireworks):
    """Stands in for the host: records calls, spends nothing."""
    def __init__(self, delete_seconds=0.0, ready=True):
        self.account, self.created, self.deletes, self.delete_seconds, self.ready = ACCOUNT, 0, 0, delete_seconds, ready
        distill._ACCOUNTS.add(ACCOUNT)

    def create_deployment(self, *a, **k):
        self.created += 1
        return {"name": f"accounts/{ACCOUNT}/deployments/d1"}

    def deployment(self, _):
        if not self.ready:
            raise RuntimeError("host error")
        return {"state": "READY"}

    def load_adapter(self, *a):
        return {}

    def delete_deployment(self, _):
        time.sleep(self.delete_seconds)
        self.deletes += 1


def args(**kw):
    return Namespace(**{"approve_usd": 10.0, "max_minutes": 60.0, "accelerator": "X", "accelerator_count": 1, "usd_per_gpu_hour": 8.0, **kw})


def use(dg, monkeypatch, host, attempt=None):
    monkeypatch.setattr(distill.Fireworks, "from_env", classmethod(lambda cls: host))
    monkeypatch.setattr(dg, "first_try", attempt or (lambda d, m, t, s: {"trial": t, "passed": True, "translated": True, "compiled": True}))


def stored(dg):
    return json.loads((dg.DIR / "evaluation.json").read_text())


def not_found():
    request = httpx.Request("POST", "http://fake.invalid")
    return openai.NotFoundError("no such model", response=httpx.Response(404, request=request), body=None)


def test_a_clean_run_counts_every_attempt_and_deletes_the_deployment(dg, monkeypatch):
    host = FakeHost()
    use(dg, monkeypatch, host)
    assert dg.evaluate(args()) == 0
    state = stored(dg)
    assert state["status"] == "complete" and host.deletes == 1 and state["deployment"]["deleted"] is True
    assert "openSince" not in state["deployment"]
    assert dg.total(state["programs"], "tuned") == {"attempts": 4, "passed": 4, "compiled": 4, "programsWithAPass": 4, "lostToHost": 0}


def test_a_404_on_the_tuned_model_is_the_hosts_fault_not_zero_of_twelve(dg, monkeypatch):
    host = FakeHost()

    def attempt(d, model, trial, s):
        if "models/diocle" in model:
            raise not_found()
        return {"trial": trial, "passed": True, "translated": True, "compiled": True}

    use(dg, monkeypatch, host, attempt)
    dg.evaluate(args())
    state = stored(dg)
    tuned = dg.total(state["programs"], "tuned")
    assert tuned["attempts"] == 0 and tuned["passed"] == 0 and tuned["lostToHost"] == 4
    assert state["status"] == "partial" and state["infrastructureLog"]


def test_first_try_raises_host_errors_instead_of_recording_a_model_failure(dg, monkeypatch):
    import diocle_converter.translate as translate

    def refuse(*a, **k):
        raise not_found()

    monkeypatch.setattr(translate, "translate", refuse)
    settings = dg.replace(dg_settings(), model="m")
    with pytest.raises(openai.APIError):
        dg.first_try("eval/samples/chqclr", "m", 1, settings)


def dg_settings():
    from diocle_converter.config import Settings
    return Settings.from_env()


def test_a_bad_answer_does_count_against_the_model(dg, monkeypatch):
    import diocle_converter.translate as translate

    def bad_answer(*a, **k):
        raise ValueError("not JSON")

    monkeypatch.setattr(translate, "translate", bad_answer)
    rec = dg.first_try("eval/samples/chqclr", "m", 1, dg_settings())
    assert rec["passed"] is False and rec["translated"] is False and "infrastructureFailure" not in rec


def test_attempts_lost_to_the_host_run_again_on_resume(dg, monkeypatch):
    host = FakeHost()
    lost = {"trial": 1, "passed": False, "infrastructureFailure": True}
    done = {"trial": 1, "passed": True, "translated": True}
    programs = {n: {"base": [done], "tuned": [done]} for n in dg.HELD_OUT_DIRS}
    programs["CHQCLR"]["tuned"] = [lost]
    (dg.DIR / "evaluation.json").write_text(json.dumps({"status": "partial", "programs": programs, "infrastructureLog": [], "deployment": {}}))
    calls = []
    use(dg, monkeypatch, host, lambda d, m, t, s: calls.append(d) or {"trial": t, "passed": True, "translated": True})
    dg.evaluate(args())
    assert calls == ["eval/samples/chqclr"] and stored(dg)["status"] == "complete"


def test_nothing_left_to_do_creates_no_deployment(dg, monkeypatch):
    host = FakeHost()
    done = {"trial": 1, "passed": True}
    (dg.DIR / "evaluation.json").write_text(json.dumps({"programs": {n: {"base": [done], "tuned": [done]} for n in dg.HELD_OUT_DIRS},
                                                        "infrastructureLog": [], "deployment": {}}))
    use(dg, monkeypatch, host)
    assert dg.evaluate(args()) == 0 and host.created == 0


def test_the_owners_limit_covers_every_run_of_the_evaluation(dg, monkeypatch):
    host = FakeHost()
    (dg.DIR / "evaluation.json").write_text(json.dumps({"programs": {}, "infrastructureLog": [], "deployment": {"estimatedUsd": 10.0, "minutes": 75}}))
    use(dg, monkeypatch, host)
    with pytest.raises(SystemExit, match="already spent"):
        dg.evaluate(args(approve_usd=10.0))
    assert host.created == 0


def test_a_resume_gets_only_what_is_left_of_the_limit(dg, monkeypatch, capsys):
    host = FakeHost()
    (dg.DIR / "evaluation.json").write_text(json.dumps({"programs": {}, "infrastructureLog": [], "deployment": {"estimatedUsd": 6.0}}))
    use(dg, monkeypatch, host)
    dg.evaluate(args(approve_usd=10.0, max_minutes=600.0))
    assert "limit: 30 min, about $4.00" in capsys.readouterr().out


def test_a_crashed_run_with_an_unknown_cost_stops_a_resume(dg, monkeypatch):
    host = FakeHost()
    (dg.DIR / "evaluation.json").write_text(json.dumps({"programs": {}, "infrastructureLog": [], "deployment": {"openSince": "2026-11-02T00:00:00Z"}}))
    use(dg, monkeypatch, host)
    with pytest.raises(SystemExit, match="did not finish cleanly"):
        dg.evaluate(args())
    assert host.created == 0


def test_the_deployment_is_deleted_when_the_wait_fails(dg, monkeypatch):
    host = FakeHost(ready=False)
    use(dg, monkeypatch, host)
    with pytest.raises(RuntimeError):
        dg.evaluate(args())
    assert host.deletes == 1 and "openSince" not in stored(dg)["deployment"]


def test_a_failed_delete_is_kept_on_record_so_nothing_resumes_on_top_of_it(dg, monkeypatch, capsys):
    host = FakeHost()

    def refuse(_):
        raise RuntimeError("no")

    host.delete_deployment = refuse
    monkeypatch.setattr(dg.time, "sleep", lambda _: None)
    use(dg, monkeypatch, host)
    dg.evaluate(args())
    state = stored(dg)
    assert state["deployment"]["deleted"] is False and state["deployment"]["openSince"]
    assert "DELETE FAILED" in capsys.readouterr().out


def test_the_watchdog_ends_the_run_and_cap_ended_attempts_are_not_failures(dg, monkeypatch):
    host = FakeHost()

    def slow(d, m, t, s):
        time.sleep(0.4)
        raise not_found()

    use(dg, monkeypatch, host, slow)
    dg.evaluate(args(max_minutes=0.002))  # 0.12 s
    state = stored(dg)
    assert host.deletes == 1 and state["status"] == "partial"
    assert all(dg.total(state["programs"], w)["attempts"] == 0 for w in ("base", "tuned"))


def test_a_delete_in_flight_finishes_before_evaluate_returns(dg, monkeypatch):
    host = FakeHost(delete_seconds=0.3)

    def slow(d, m, t, s):
        time.sleep(0.2)
        return {"trial": t, "passed": True, "translated": True}

    use(dg, monkeypatch, host, slow)
    dg.evaluate(args(max_minutes=0.002))
    assert host.deletes == 1 and stored(dg)["deployment"]["deleted"] is True


def test_the_account_name_stays_out_of_result_files_and_errors(dg, monkeypatch):
    host = FakeHost()

    def attempt(d, m, t, s):
        raise RuntimeError(f"model {m} failed")

    use(dg, monkeypatch, host, attempt)
    dg.evaluate(args())
    assert ACCOUNT not in (dg.DIR / "evaluation.json").read_text() and ACCOUNT not in (dg.DIR / "results.json").read_text()


def test_report_refuses_to_write_the_account_name():
    distill._ACCOUNTS.add(ACCOUNT)
    try:
        with pytest.raises(ValueError, match="account name"):
            distill.assert_scrubbed(f"accounts/{ACCOUNT}/models/x")
        assert distill.scrub(f"accounts/{ACCOUNT}/models/x") == "accounts/<account>/models/x"
    finally:
        distill._ACCOUNTS.clear()


def test_a_blocked_upload_is_recorded_not_hidden(dg, monkeypatch, tmp_path):
    host = FakeHost()

    def refuse(*a):
        raise RuntimeError(f"POST /accounts/{ACCOUNT}/datasets: 403 uploads disabled")

    host.upload_dataset = refuse
    monkeypatch.setattr(dg, "TRAIN", tmp_path / "train.jsonl")
    monkeypatch.setattr(dg, "held_out_sources", lambda: {})
    (tmp_path / "train.jsonl").write_text(json.dumps({"messages": [{"role": "user", "content": "x"}]}) + "\n")
    monkeypatch.setattr(distill.Fireworks, "from_env", classmethod(lambda cls: host))
    assert dg.train(True) == 1
    record = json.loads((tmp_path / "training.json").read_text())
    assert record["status"] == "blocked" and "403" in record["reason"] and ACCOUNT not in record["reason"]


def test_score_counts_a_stored_answer_and_leaves_unreached_attempts_unrun(dg, tmp_path, monkeypatch):
    seen = []

    def attempt(directory, model, trial, settings, client=None):
        seen.append(client.chat().message.content)
        return {"trial": trial, "passed": True, "translated": True, "compiled": True, "outputTokens": 0, "seconds": 1.0}

    monkeypatch.setattr(dg, "first_try", attempt)
    monkeypatch.setattr(dg, "report", lambda: None)
    (tmp_path / "CHQCLR-tuned-1.json").write_text(json.dumps(
        {"text": ' to=user<|message|>{"mainClass": "wrong", "javaSource": "class C {}", "notes": ""}<|eot|>', "outputTokens": 9, "seconds": 7.5}))
    assert dg.score(Namespace(dir=str(tmp_path), minutes=60.0)) == 0
    state = json.loads((dg.DIR / "evaluation.json").read_text())
    assert state["status"] == "partial"
    assert len(state["programs"]["CHQCLR"]["tuned"]) == 1 and state["programs"]["CHQCLR"]["base"] == []
    assert state["programs"]["CHQCLR"]["tuned"][0]["seconds"] == 7.5
    assert state["deployment"]["estimatedUsd"] == 6.5
    assert json.loads(seen[0])["mainClass"] != "wrong"
