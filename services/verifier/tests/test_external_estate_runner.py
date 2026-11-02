"""eval/run_external_estate.py against a TEST DOUBLE for the converter: no model call anywhere in this file. The double
is a real process, so timeouts, process groups, stderr and exit codes are real; only the last test uses the real toolchain."""
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "eval" / "run_external_estate.py"
SINGLE, DISPLAY = REPO / "samples" / "loyalty-waiver", REPO / "samples" / "display-report"  # stored Java that matches

FAKE_CONVERTER = r'''
import json, os, shutil, subprocess, sys, time
from pathlib import Path
sample, root = Path(sys.argv[2]), Path(os.environ["FAKE_ROOT"])
with (root / "calls").open("a") as f:
    f.write(sample.name + "\n")
assert sys.argv[1] == "run" and sys.argv[3:] == ["--breaker", "--no-memory", "--max-usd", "0.4"]
print("model: fake-model (hosted), reasoning_effort=medium, caps: 60 calls/run, 20/round, 3 rounds", flush=True)
b = json.loads((sample / "fake.json").read_text()) if (sample / "fake.json").exists() else {}
run_id = f"{sample.name}-{time.strftime('%Y%m%d-%H%M%S')}"
print(f"run started runs/{run_id}", flush=True)
run = root / "runs" / run_id
if b.get("hang"):
    run.mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"status": "running", "certified": False, "rounds": [], "usage": {"estimatedCostUsd": 0.07, "calls": 2}}))
    subprocess.Popen([sys.executable, "-c", f"import time, pathlib; time.sleep(2.5); pathlib.Path({str(root / 'child-alive')!r}).write_text('x')"])
    time.sleep(60)
print(b.get("stderr", ""), file=sys.stderr, flush=True)
if b.get("crash"):
    sys.exit(3)
run.mkdir(parents=True)
if (sample / "java-conversion").exists():
    shutil.copytree(sample / "java-conversion", run / "java")
(run / "events.jsonl").write_text("".join(json.dumps({"message": m}) + "\n" for m in b.get("events", ["a", "b", "c", "d"])))
certified = b.get("certified", True)
time.sleep(b.get("delay", 0))
(run / "run.json").write_text(json.dumps({"certified": certified, "status": "certified" if certified else "not-certified", "error": b.get("error"), "rounds": [{}],
    "guard": {"blocked": False, "stopped": 0, "review": {"verdict": b.get("guard", "pass"), "summary": "reviewed"}},
    "usage": {"estimatedCostUsd": b.get("usd", 0.01) if b.get("usd", 0.01) != "unpriced" else None, "calls": 3, "modelCalls": ["left out"]},
    "breaker": b.get("breaker", {"tried": 12, "broke": 0})}))
print(f"run saved to runs/{run_id}")
sys.exit(0 if certified else 1)
'''


@pytest.fixture
def estate(tmp_path, monkeypatch):
    """The runner module pointed at a throwaway tree, with a report the test fills in through add()."""
    spec = importlib.util.spec_from_file_location("run_external_estate", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (tmp_path / "eval").mkdir()
    fake = tmp_path / "fake_converter.py"
    fake.write_text(FAKE_CONVERTER)
    for name, value in {"ROOT": tmp_path, "WORK": tmp_path / "work", "REPORT": tmp_path / "work" / "report.json",
                        "SAMPLES": tmp_path / "work" / "samples", "OUT": tmp_path / "eval" / "results.json",
                        "PARTIAL": tmp_path / "work" / "results.partial.json", "CONVERTER": [sys.executable, str(fake)],
                        "CONVERTER_CWD": tmp_path, "LOGS": tmp_path / "work" / "logs", "PREFLIGHT": [sys.executable, "-c", ""], "REQUIRED_TOOLS": []}.items():
        monkeypatch.setattr(mod, name, value)
    monkeypatch.setenv("FAKE_ROOT", str(tmp_path))
    monkeypatch.setattr(mod, "verify_sample", lambda *a, **k: {"results": [], "summary": {"total": 1000, "failed": 0},
                                                               "runs": {"exitCodeMatch": True, "stdoutMatch": True, "original": {"compiled": True}, "converted": {"compiled": True}}})
    monkeypatch.setattr(mod, "passes", lambda report: True)
    (tmp_path / "work").mkdir()
    mod.programs = []

    def add(name, origin=SINGLE, path=None, fake_behaviour=None, convertible=True, reason=None, no_input=False):
        mod.programs.append({"name": name, "path": path or f"{name}.cobol", "convertible": convertible, "notConvertibleReason": reason})
        sample = mod.SAMPLES / name.lower()
        if convertible and not sample.exists():
            shutil.copytree(origin, sample)
            meta = json.loads((sample / "sample.json").read_text())
            if no_input:  # like the estate's HELLO: nothing to seed
                meta["files"] = []
            (sample / "sample.json").write_text(json.dumps({**meta, "program": name}))
            if fake_behaviour:
                (sample / "fake.json").write_text(json.dumps(fake_behaviour))

    def write_report(commit=mod.PINNED_COMMIT):
        mod.REPORT.write_text(json.dumps({"source": {"commit": commit}, "programs": mod.programs}))
        mod.SAMPLES.mkdir(exist_ok=True)

    mod.add, mod.write_report = add, write_report
    mod.calls = lambda: (tmp_path / "calls").read_text().split() if (tmp_path / "calls").exists() else []
    mod.tmp = tmp_path
    return mod


def by_path(mod, path=None):
    data = json.loads((path or mod.OUT).read_text())
    return data, {r["path"]: r for r in data["results"]}


def test_every_program_gets_exactly_one_outcome_and_the_collision_is_not_called_the_same_program(estate):
    estate.add("REFUSED", convertible=False, reason="ACCEPT reads the console")
    estate.add("CBL0006", path="CBL0006.cobol")
    estate.add("CBL0006", path="CBLC1.cobol")
    estate.add("NOSAMPLE")
    shutil.rmtree(estate.SAMPLES / "nosample")
    estate.add("FAILS", fake_behaviour={"certified": False, "error": "repair ran out of rounds"})
    estate.write_report()
    estate.run_estate(5.0)
    data, r = by_path(estate)
    assert [r[p]["outcome"] for p in ("REFUSED.cobol", "CBL0006.cobol", "CBLC1.cobol", "NOSAMPLE.cobol", "FAILS.cobol")] == [
        "refused", "certified", "not converted", "not run", "not certified"]
    assert r["REFUSED.cobol"]["reason"] == "ACCEPT reads the console"
    assert "CBL0006.cobol" in r["CBLC1.cobol"]["reason"] and "never converted" in r["CBLC1.cobol"]["reason"]
    assert "same program" not in r["CBLC1.cobol"]["reason"]
    assert estate.calls() == ["cbl0006", "fails"]  # converted once each; nothing for the refused or the collision
    assert data["complete"] is True and data["programsAccounted"] == 5 and not estate.PARTIAL.exists()
    assert data["recordedCostUsd"] == 0.02 and "modelCalls" not in r["CBL0006.cobol"]["usage"]
    assert r["CBL0006.cobol"]["model"] == "fake-model" and r["CBL0006.cobol"]["caps"] == "60 calls/run, 20/round, 3 rounds"


def test_a_certification_says_what_was_exercised(estate):
    estate.add("ATTACKED")
    estate.add("SKIPPED", fake_behaviour={"breaker": {"tried": 0, "skipped": "multi-file program"}})
    estate.add("FIXED", origin=DISPLAY, no_input=True, fake_behaviour={"breaker": {"tried": 0, "skipped": "display-only program"}})
    estate.write_report()
    tally = estate.run_estate(5.0)
    assert tally == {"certified, inputs vary, attacked": 1, "certified, inputs vary, not attacked": 1, "certified, inputs never vary": 1}
    data, r = by_path(estate)
    attacked = r["ATTACKED.cobol"]["exercised"]
    assert attacked["shape"] == "single-file" and attacked["seedsChangeInputs"] is True and attacked["breakerCanRun"] is True
    assert 0 < len(attacked["fieldsVaried"]) <= attacked["fieldsTotal"]
    assert r["FIXED.cobol"]["exercised"]["shape"] == "display-only" and r["FIXED.cobol"]["exercised"]["seedsChangeInputs"] is False
    assert data["tally"] == tally and [s["seed"] for s in r["ATTACKED.cobol"]["freshSeeds"]] == estate.FRESH_SEEDS


def test_a_field_counts_as_varied_only_if_a_new_seed_changes_it(estate):
    meta = json.loads((SINGLE / "sample.json").read_text())
    fields = estate.load_fields(meta["layouts"]["input"])
    varied = estate.exercise(SINGLE)["fieldsVaried"]
    assert set(varied) <= {f.name for f in fields}
    for f in fields:
        if f.kind == "alnum" and not f.values:  # placeholders that number the record, the same under every seed
            assert f.name not in varied


@pytest.mark.parametrize("commit", [None, "", "0" * 40, "780b1c9624e0"])
def test_a_missing_moved_or_abbreviated_commit_is_refused_before_anything_runs(estate, commit):
    estate.add("ONE")
    estate.write_report(commit)
    with pytest.raises(SystemExit, match="pins"):
        estate.run_estate(5.0)
    assert estate.calls() == [] and not estate.OUT.exists() and not estate.PARTIAL.exists()
    with pytest.raises(SystemExit, match="pins"):
        estate.plan()


def test_results_survive_a_killed_run_and_the_resume_does_not_pay_twice(estate, monkeypatch):
    for name in ("ONE", "TWO", "THREE"):
        estate.add(name)
    estate.write_report()
    real = estate.convert

    def killed_on_two(sample, program):
        if program == "TWO":
            raise KeyboardInterrupt
        return real(sample, program)

    monkeypatch.setattr(estate, "convert", killed_on_two)
    with pytest.raises(KeyboardInterrupt):
        estate.run_estate(5.0)
    saved = json.loads(estate.PARTIAL.read_text())
    assert saved["complete"] is False and [r["program"] for r in saved["results"]] == ["ONE"] and not estate.OUT.exists()
    monkeypatch.setattr(estate, "convert", real)
    with pytest.raises(SystemExit, match="ceiling"):  # a resume keeps the settings
        estate.run_estate(9.0)
    estate.run_estate(5.0)
    data, r = by_path(estate)
    assert estate.calls() == ["one", "two", "three"] and data["resumes"] == 1 and data["complete"] is True and len(r) == 3


def test_a_failed_fresh_seed_or_an_unmeasured_program_is_not_reported_as_a_clean_certification(estate, monkeypatch):
    estate.add("SEEDFAIL")
    estate.add("UNMEASURED")
    estate.write_report()
    monkeypatch.setattr(estate, "passes", lambda report: False)
    real = estate.exercise
    monkeypatch.setattr(estate, "exercise", lambda s: (_ for _ in ()).throw(ValueError("x")) if s.name == "unmeasured" else real(s))
    estate.run_estate(5.0)
    _, r = by_path(estate)
    assert estate.level(r["SEEDFAIL.cobol"]) == "certified, then failed a fresh seed"
    assert "error" in r["UNMEASURED.cobol"]["exercised"] and r["UNMEASURED.cobol"]["outcome"] == "certified"
    r["UNMEASURED.cobol"]["freshSeeds"] = [{"passed": True}]
    assert estate.level(r["UNMEASURED.cobol"]) == "certified, what it exercised is unknown"


def test_a_provider_failure_stops_the_run_records_no_verdict_and_the_resume_finishes(estate):
    estate.add("OK")
    estate.add("OUTAGE", fake_behaviour={"certified": False, "error": "RateLimitError (HTTP 429)", "usd": 0.03})
    estate.add("LATER")
    estate.write_report()
    with pytest.raises(SystemExit, match="provider failure"):
        estate.run_estate(5.0)
    saved = json.loads(estate.PARTIAL.read_text())
    assert [r["program"] for r in saved["results"]] == ["OK"] and estate.calls() == ["ok", "outage"]
    (estate.SAMPLES / "outage" / "fake.json").write_text("{}")
    time.sleep(1.1)  # a run directory is named to the second
    estate.run_estate(5.0)
    data, r = by_path(estate)
    assert r["OUTAGE.cobol"]["outcome"] == "certified" and data["restartedPrograms"] == ["outage"]
    assert data["recordedCostUsd"] == 0.06 and data["resumes"] == 1  # the interrupted attempt's spend stays counted


def test_nothing_runs_without_the_toolchain_or_the_keys_and_no_program_is_marked_failed(estate, monkeypatch):
    estate.add("ONE")
    estate.write_report()
    monkeypatch.setattr(estate, "REQUIRED_TOOLS", ["no-such-compiler"])
    with pytest.raises(SystemExit, match="no-such-compiler"):
        estate.run_estate(5.0)
    monkeypatch.setattr(estate, "REQUIRED_TOOLS", [])
    monkeypatch.setattr(estate, "PREFLIGHT", [sys.executable, "-c", "raise ValueError('secret-in-message')"])
    with pytest.raises(SystemExit, match="ValueError") as e:
        estate.run_estate(5.0)
    assert "secret-in-message" not in str(e.value) and estate.calls() == [] and not estate.PARTIAL.exists()


def test_a_resume_refuses_a_changed_diocle_and_a_real_run_refuses_uncommitted_changes(estate, monkeypatch):
    estate.add("ONE")
    estate.write_report()
    estate.PARTIAL.write_text(json.dumps({"maxTotalUsd": 5.0, "diocleCommit": "older", "resumes": 0, "results": [], "startedAt": "20260101-000000"}))
    monkeypatch.setattr(estate, "_git", lambda *a: "newer" if a[0] == "rev-parse" else "")
    with pytest.raises(SystemExit, match="tuning"):
        estate.run_estate(5.0)
    monkeypatch.setattr(estate, "_git", lambda *a: " M services/x.py" if a[0] == "status" else "newer")
    with pytest.raises(SystemExit, match="changes"):
        estate.run_estate(5.0)
    assert estate.calls() == []


def test_ctrl_c_stops_running_conversions_and_saves_what_finished(estate, monkeypatch):
    monkeypatch.setattr(estate, "TIMEOUT_MINUTES", 5)
    estate.add("HANGS", fake_behaviour={"hang": True})
    estate.write_report()
    import threading
    threading.Timer(1.5, lambda: (estate._kill_running())).start()  # what the main thread does on KeyboardInterrupt
    real_work_stop = estate.convert
    started = time.time()
    with pytest.raises(BaseException):
        monkeypatch.setattr(estate, "convert", lambda s, p: (real_work_stop(s, p), (_ for _ in ()).throw(KeyboardInterrupt()))[0])
        estate.run_estate(5.0)
    assert time.time() - started < 30
    time.sleep(2.5)
    assert not (estate.tmp / "child-alive").exists() and not estate.OUT.exists()


def test_a_hung_conversion_times_out_stops_its_children_and_the_run_goes_on(estate, monkeypatch):
    monkeypatch.setattr(estate, "TIMEOUT_MINUTES", 0.02)
    estate.add("HANGS", fake_behaviour={"hang": True})
    estate.add("AFTER")
    estate.write_report()
    estate.run_estate(5.0)
    data, r = by_path(estate)
    assert r["HANGS.cobol"]["outcome"] == "not certified" and r["HANGS.cobol"]["exitCode"] is None
    assert "timed out" in r["HANGS.cobol"]["error"] and r["AFTER.cobol"]["outcome"] == "certified"
    assert data["recordedCostUsd"] == 0.08 and data["costComplete"] is True and r["HANGS.cobol"]["usage"]["calls"] == 2  # the live record counts
    time.sleep(2.5)
    assert not (estate.tmp / "child-alive").exists()


def test_a_failure_keeps_stderr_and_events_with_no_local_path_or_key(estate):
    estate.add("FAILS", fake_behaviour={"certified": False, "error": "no luck", "events": ["1", "2", "3", "4"],
                                        "stderr": f"boom in {estate.tmp}/x.py api_key=abc123secret Authorization: Bearer zzz999"})
    estate.add("CRASHES", fake_behaviour={"crash": True, "stderr": "Traceback:\nValueError: provider says your account 12345"})
    estate.write_report()
    estate.run_estate(5.0)
    data, r = by_path(estate)
    failed = r["FAILS.cobol"]
    assert failed["error"] == "no luck" and failed["lastEvents"] == ["2", "3", "4"]
    text = json.dumps(data)
    assert str(estate.tmp) not in text and "abc123secret" not in text and "zzz999" not in text and "stderrTail" not in text
    crashed = r["CRASHES.cobol"]
    assert crashed["outcome"] == "not certified" and crashed["exitCode"] == 3
    assert "no run record" in crashed["error"] and "(ValueError)" in crashed["error"] and "provider says" not in crashed["error"]
    logs = "".join(p.read_text() for p in estate.LOGS.iterdir())  # the whole story stays in the git-ignored logs
    assert "abc123secret" in logs and "provider says" in logs


def test_the_spending_ceiling_stops_new_programs_and_still_accounts_for_every_program(estate):
    estate.add("DEAR", fake_behaviour={"usd": 0.3})
    estate.add("NEXT")
    estate.add("REFUSED", convertible=False, reason="EXEC SQL")
    estate.write_report()
    estate.run_estate(0.5)
    data, r = by_path(estate)
    assert estate.calls() == ["dear"]
    assert r["NEXT.cobol"]["outcome"] == "not run" and "$0.50" in r["NEXT.cobol"]["reason"]
    assert r["REFUSED.cobol"]["outcome"] == "refused" and data["programsAccounted"] == 3 and data["maxTotalUsd"] == 0.5


def test_a_program_that_breaks_the_runner_is_reported_and_the_run_goes_on(estate, monkeypatch):
    estate.add("BAD")
    estate.add("GOOD")
    estate.write_report()
    real = estate.convert
    monkeypatch.setattr(estate, "convert", lambda s, p: (_ for _ in ()).throw(ValueError("corrupt")) if p == "BAD" else real(s, p))
    estate.run_estate(5.0)
    _, r = by_path(estate)
    assert r["BAD.cobol"]["outcome"] == "not certified" and "corrupt" in r["BAD.cobol"]["error"] and r["GOOD.cobol"]["outcome"] == "certified"


def test_finished_results_are_never_overwritten(estate):
    estate.add("ONE")
    estate.write_report()
    estate.OUT.write_text("{}")
    with pytest.raises(SystemExit, match="never overwritten"):
        estate.run_estate(5.0)
    assert estate.OUT.read_text() == "{}" and estate.calls() == []


def test_a_real_run_cannot_start_without_an_approved_ceiling():
    proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 2 and "--max-total-usd" in proc.stderr


def test_the_plan_calls_no_converter_and_flags_what_will_not_vary(estate):
    estate.add("REFUSED", convertible=False, reason="EXEC SQL")
    estate.add("VARIES")
    estate.add("FIXED", origin=DISPLAY, no_input=True)
    estate.write_report()
    rows = {r["program"]: r for r in estate.plan()}
    assert rows["REFUSED"]["outcome"] == "refused" and rows["VARIES"]["exercised"]["seedsChangeInputs"] is True
    assert rows["FIXED"]["exercised"]["seedsChangeInputs"] is False and estate.calls() == []


@pytest.mark.toolchain
def test_end_to_end_with_real_cobc_and_java_and_only_the_model_faked(estate, monkeypatch):
    """Stored Java stands in for the model's: compile, run and compare are real, on both program shapes."""
    from diocle_verifier.verify import passes, verify_sample
    monkeypatch.setattr(estate, "verify_sample", verify_sample)
    monkeypatch.setattr(estate, "passes", passes)
    estate.add("LOYWAIVE", path="fee.cobol")
    estate.add("TXNLIST", origin=DISPLAY, path="list.cobol", fake_behaviour={"breaker": {"tried": 0, "skipped": "display-only program"}})
    estate.write_report()
    estate.run_estate(5.0)
    data, r = by_path(estate)
    for path in ("fee.cobol", "list.cobol"):
        seeds = r[path]["freshSeeds"]
        assert [s["seed"] for s in seeds] == estate.FRESH_SEEDS
        assert all(s["passed"] and s["cases"] > 0 and s["failed"] == 0 for s in seeds), seeds
    assert data["tally"] == {"certified, inputs vary, attacked": 1, "certified, inputs vary, not attacked": 1}
    assert data["cobc"].startswith("cobc") and "not found" not in data["java"]


def test_parallel_conversions_keep_report_order_and_reserve_for_what_is_running(estate):
    for name in ("A", "B", "C", "D"):
        estate.add(name, fake_behaviour={"usd": 0.01})
    estate.add("REFUSED", convertible=False, reason="EXEC SQL")
    estate.write_report()
    estate.run_estate(5.0, workers=3)
    data, r = by_path(estate)
    assert [x["program"] for x in data["results"]] == ["A", "B", "C", "D", "REFUSED"] and sorted(estate.calls()) == ["a", "b", "c", "d"]
    assert data["workers"] == 3 and data["tally"]["certified, inputs vary, attacked"] == 4


def test_the_ceiling_counts_programs_still_running(estate):
    """Three at once with room for two: the third waits, and goes only if the spend still leaves room."""
    for name in ("A", "B", "C"):
        estate.add(name, fake_behaviour={"usd": 0.3})
    estate.write_report()
    estate.run_estate(2 * estate.PROGRAM_CAP_USD, workers=3)
    data, r = by_path(estate)
    assert sum(x["outcome"] == "not run" for x in data["results"]) == 1 and len(estate.calls()) == 2
    assert "left no room" in next(x["reason"] for x in data["results"] if x["outcome"] == "not run")


def test_an_unpriced_run_stops_new_programs_because_the_ceiling_cannot_be_checked(estate):
    estate.add("UNPRICED", fake_behaviour={"usd": "unpriced"})
    estate.add("NEXT")
    estate.write_report()
    estate.run_estate(5.0)
    data, r = by_path(estate)
    assert estate.calls() == ["unpriced"] and r["NEXT.cobol"]["outcome"] == "not run"
    assert "unknown" in r["NEXT.cobol"]["reason"] and data["costComplete"] is False


def test_a_fresh_seed_that_blows_up_is_a_failed_seed_not_a_lost_program(estate, monkeypatch):
    estate.add("ONE")
    estate.write_report()
    monkeypatch.setattr(estate, "verify_sample", lambda *a, **k: (_ for _ in ()).throw(KeyError("runs")))
    estate.run_estate(5.0)
    _, r = by_path(estate)
    assert r["ONE.cobol"]["outcome"] == "certified" and estate.level(r["ONE.cobol"]) == "certified, then failed a fresh seed"
    assert r["ONE.cobol"]["runId"] and "KeyError" in r["ONE.cobol"]["freshSeeds"][0]["error"]


def test_an_ordinary_failure_is_not_called_an_unfinished_run_and_the_guard_verdict_is_recorded(estate):
    estate.add("REPAIRFAILS", fake_behaviour={"certified": False})
    estate.add("GUARDDOWN", fake_behaviour={"guard": "error"})
    estate.add("CLEAN")
    estate.write_report()
    estate.run_estate(5.0)
    data, r = by_path(estate)
    assert r["REPAIRFAILS.cobol"]["outcome"] == "not certified" and r["REPAIRFAILS.cobol"]["error"] is None
    assert r["REPAIRFAILS.cobol"]["status"] == "not-certified" and r["REPAIRFAILS.cobol"]["lastEvents"] == ["b", "c", "d"]
    assert r["GUARDDOWN.cobol"]["guard"]["reviewVerdict"] == "error" and data["certifiedWithoutGuardPass"] == ["GUARDDOWN"]


def test_a_provider_stop_keeps_a_conversion_that_already_finished(estate, monkeypatch):
    estate.add("FINISHED")
    estate.add("OUTAGE", fake_behaviour={"certified": False, "error": "APIConnectionError", "delay": 0.5})
    estate.write_report()
    stub = estate.verify_sample
    monkeypatch.setattr(estate, "verify_sample", lambda *a, **k: (time.sleep(0.5), stub(*a, **k))[1])  # still in its fresh seeds at the stop
    with pytest.raises(SystemExit, match="provider failure"):
        estate.run_estate(5.0, workers=2)
    saved = json.loads(estate.PARTIAL.read_text())
    assert [(x["program"], x["outcome"]) for x in saved["results"]] == [("FINISHED", "certified")]


@pytest.mark.parametrize("error, stops", [("RateLimitError (HTTP 429)", True), ("InternalServerError (HTTP 503)", True), ("APITimeoutError", True),
                                          ("BadRequestError (HTTP 400)", False), ("spend cap: $0.39 spent", False), ("repair ran out of rounds", False)])
def test_only_an_outage_counts_as_a_provider_failure(estate, error, stops):
    assert bool(estate.PROVIDER_FAILURE.search(error)) is stops

