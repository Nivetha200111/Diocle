"""Visitor imports: programs whose original does not compile are skipped before any model call and use no slot."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from diocle_api import deliver, public


def make_samples(tmp_path, names, lines=10):
    for n in names:
        d = tmp_path / n.lower()
        (d / "src").mkdir(parents=True)
        (d / "src" / f"{n}.cbl").write_text("\n".join(["X"] * lines) + "\n")
        (d / "sample.json").write_text(json.dumps({"source": f"src/{n}.cbl"}))
    return [{"name": n, "path": f"cobol/{n}.cbl"} for n in names]


class FakeVerifier:
    """Stands in for `python -m diocle_verifier.precheck`: no compiler, no sandbox."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, cmd, **kw):
        name = cmd[cmd.index("-m") + 2].rsplit("/", 1)[-1].upper()
        self.calls.append((name, kw))
        answer = self.answers.get(name, {"status": "ok", "message": ""})
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(stdout=json.dumps({"version": "0.1", **answer}) + "\n", returncode=0)


@pytest.fixture(autouse=True)
def caps(monkeypatch):
    for k in ("DIOCLE_PUBLIC_MAX_PROGRAMS", "DIOCLE_PUBLIC_MAX_LINES", "DIOCLE_PUBLIC_MAX_PRECHECK",
              "DIOCLE_PUBLIC_PRECHECK_SECONDS"):
        monkeypatch.delenv(k, raising=False)


def run(tmp_path, monkeypatch, names, answers, **kw):
    programs = make_samples(tmp_path, names)
    fake = FakeVerifier(answers)
    monkeypatch.setattr(deliver.subprocess, "run", fake)
    pre = deliver.CompilePrecheck(tmp_path, kw.get("max_checks", 12), kw.get("seconds", 240))
    keep, skipped = deliver._visitor_caps(programs, tmp_path, pre)
    return [p["name"] for p in keep], skipped, fake


def test_uncompilable_programs_are_skipped_and_the_next_compilable_ones_take_the_slots(tmp_path, monkeypatch):
    bad = {"status": "fail", "diagnostics": ["CBL0001.cbl:4: error: syntax error"]}
    keep, skipped, fake = run(tmp_path, monkeypatch, ["A", "B", "C", "D", "E"], {"A": bad, "B": bad})
    assert keep == ["C", "D", "E"]
    reasons = {s["name"]: s["reason"] for s in skipped}
    assert reasons["A"].startswith("the original does not compile under GnuCOBOL -std=ibm: CBL0001.cbl:4: error")
    assert all(s["status"] == "skipped" and s["runId"] is None for s in skipped)
    assert [c[0] for c in fake.calls] == ["A", "B", "C", "D", "E"]


def test_programs_past_the_cap_are_not_checked(tmp_path, monkeypatch):
    keep, skipped, fake = run(tmp_path, monkeypatch, list("ABCDEF"), {})
    assert keep == ["A", "B", "C"] and [c[0] for c in fake.calls] == ["A", "B", "C"]
    assert "convert up to 3" in skipped[0]["reason"]


def test_over_long_programs_are_not_checked_either(tmp_path, monkeypatch):
    programs = make_samples(tmp_path, ["LONG"], lines=2000)
    fake = FakeVerifier({})
    monkeypatch.setattr(deliver.subprocess, "run", fake)
    keep, skipped = deliver._visitor_caps(programs, tmp_path, deliver.CompilePrecheck(tmp_path, 12, 240))
    assert keep == [] and not fake.calls and "lines" in skipped[0]["reason"]


def test_the_number_of_checks_is_bounded(tmp_path, monkeypatch):
    bad = {"status": "fail", "diagnostics": ["a.cbl:1: error: e"]}
    names = [f"P{i}" for i in range(20)]
    keep, skipped, fake = run(tmp_path, monkeypatch, names, {n: bad for n in names}, max_checks=5)
    assert len(fake.calls) == 5
    assert keep == ["P5", "P6", "P7"]  # past the bound the rest proceed unchecked, as before


def test_the_total_time_is_bounded(tmp_path, monkeypatch):
    keep, skipped, fake = run(tmp_path, monkeypatch, ["A", "B", "C"], {}, seconds=-1)
    assert keep == ["A", "B", "C"] and not fake.calls


def test_each_check_waits_at_most_what_is_left_and_runs_with_a_minimal_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("META_API_KEY", "secret-value")
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox:8100")
    _, _, fake = run(tmp_path, monkeypatch, ["A"], {}, seconds=5)
    env, cmd_timeout = fake.calls[0][1]["env"], fake.calls[0][1]["timeout"]
    assert "META_API_KEY" not in env and env["DIOCLE_SANDBOX_URL"] == "http://sandbox:8100"
    assert cmd_timeout <= 5 + 120


def test_an_unavailable_sandbox_does_not_block_and_the_check_stops_after_two_unknowns(tmp_path, monkeypatch):
    unknown = {"status": "unknown", "note": "the sandbox was busy"}
    names = ["A", "B", "C", "D"]
    keep, skipped, fake = run(tmp_path, monkeypatch, names, {n: unknown for n in names})
    assert keep == ["A", "B", "C"] and len(fake.calls) == 2  # C and beyond: no more asking


def test_garbage_or_crashes_count_as_no_answer(tmp_path, monkeypatch):
    answers = {"A": subprocess.TimeoutExpired("x", 1), "B": OSError("no venv")}
    keep, _, fake = run(tmp_path, monkeypatch, ["A", "B", "C"], answers)
    assert keep == ["A", "B", "C"]
    programs = make_samples(tmp_path, ["Z"])
    monkeypatch.setattr(deliver.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="not json", stderr="", returncode=1))
    assert deliver.CompilePrecheck(tmp_path, 3, 10).failure("Z") is None


def test_a_long_reason_is_cut(tmp_path, monkeypatch):
    _, skipped, _ = run(tmp_path, monkeypatch, ["A"], {"A": {"status": "fail", "diagnostics": ["m" * 5000, "b", "c", "d", "e"]}})
    assert len(skipped[0]["reason"]) < 700


def test_limits_are_configurable_and_default_bounded(monkeypatch):
    assert public.limits()["maxPrecheck"] == 12 and public.limits()["precheckSeconds"] == 240
    monkeypatch.setenv("DIOCLE_PUBLIC_MAX_PRECHECK", "4")
    assert public.limits()["maxPrecheck"] == 4


def test_no_precheck_object_keeps_the_old_behaviour(tmp_path):
    programs = make_samples(tmp_path, list("ABCD"))
    keep, skipped = deliver._visitor_caps(programs, tmp_path)
    assert [p["name"] for p in keep] == ["A", "B", "C"] and len(skipped) == 1


def test_an_unreadable_precheck_is_logged_with_the_stderr_tail_and_recorded(tmp_path, monkeypatch, capsys):
    make_samples(tmp_path, ["Z"])
    monkeypatch.setattr(deliver.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout="", stderr="Traceback ...\nModuleNotFoundError: No module named 'diocle_verifier'\n", returncode=1))
    pre = deliver.CompilePrecheck(tmp_path, 3, 10)
    assert pre.failure("Z") is None
    assert "ModuleNotFoundError" in capsys.readouterr().out  # the raw tail goes to the server-side log only
    assert pre.record()["notes"] == [deliver.NOTE_UNREADABLE] and pre.record()["checked"] == 1
    assert "ModuleNotFoundError" not in json.dumps(pre.record())


def test_stopping_after_two_unknowns_is_visible_with_its_reason(tmp_path, monkeypatch):
    unknown = {"status": "unknown", "note": "the sandbox was busy"}
    names = ["A", "B", "C"]
    programs = make_samples(tmp_path, names)
    monkeypatch.setattr(deliver.subprocess, "run", FakeVerifier({n: unknown for n in names}))
    pre = deliver.CompilePrecheck(tmp_path, 12, 240)
    deliver._visitor_caps(programs, tmp_path, pre)
    rec = pre.record()
    assert rec["checked"] == 2 and "did not answer twice" in rec["stopped"] and rec["notes"] == [deliver.NOTE_UNKNOWN]


def test_notes_never_carry_child_or_sandbox_text(tmp_path, monkeypatch):
    make_samples(tmp_path, ["Z"])
    monkeypatch.setattr(deliver.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stdout=json.dumps({"status": "unknown", "note": "TOPSECRET sandbox body"}) + "\n", stderr="TOPSECRET", returncode=0))
    pre = deliver.CompilePrecheck(tmp_path, 3, 10)
    pre.failure("Z")

    def boom(*a, **k):
        raise OSError("TOPSECRET path")

    monkeypatch.setattr(deliver.subprocess, "run", boom)
    pre.failure("Z")
    assert "TOPSECRET" not in json.dumps(pre.record())


def test_a_failure_without_diagnostics_is_not_believed(tmp_path, monkeypatch):
    _, skipped, _ = run(tmp_path, monkeypatch, ["A"], {"A": {"status": "fail", "message": "old shape"}})
    assert skipped == []
