"""Convert-anyway delivery: labels, the repo spend cap, the visitor firewall, contracts. Converter and analyzer are TEST DOUBLES."""

import json
import subprocess
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from diocle_api import deliver, deliveries
from diocle_api.app import app

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
DELIVERY = json.loads((CONTRACTS / "delivery.schema.json").read_text())
RUN = json.loads((CONTRACTS / "run.schema.json").read_text())
SRC = {"location": "https://github.com/o/r", "commit": "a" * 40}


def fake_run(run_id, assurance, reason, cost, certified=False):
    return {"id": run_id, "certified": certified, "assurance": assurance, "assuranceReason": reason, "error": reason,
            "efficiency": {"estimatedCostUsd": cost}, "model": "m", "after": None, "usage": {}}


# ---- the main loop with test doubles -----------------------------------------------------------

@pytest.fixture
def delivery_env(tmp_path, monkeypatch):
    monkeypatch.setattr(deliver, "REPO_ROOT", tmp_path)
    monkeypatch.delenv("DIOCLE_CONVERT_ANYWAY", raising=False)
    monkeypatch.delenv("REPO_MAX_USD", raising=False)
    calls = {"analyze": [], "convert": []}
    names = ["AAA", "BBB", "CCC"]
    runs = {}

    def analyze(url, delivery_id, convert_anyway=False):
        calls["analyze"].append(convert_anyway)
        programs = [{"name": n, "path": f"{n}.cbl", "convertible": n != "BBB", "notConvertibleReason": None if n != "BBB" else "EXEC SQL",
                     "copybooks": [], "copybookPaths": {}, "files": []} for n in names]
        return {"source": SRC, "programs": programs}, tmp_path / "samples"

    def convert(sample_dir, on_start=lambda r: None, flags=None, convert_anyway=False):
        name = sample_dir.name.upper()
        calls["convert"].append((name, list(flags or []), convert_anyway))
        run_id = f"{name.lower()}-20261030-000000"
        on_start(run_id)
        runs[run_id] = {"AAA": fake_run(run_id, "certified", None, 0.6, certified=True),
                        "BBB": fake_run(run_id, "compiled-unverified", "EXEC SQL needs a database or transaction adapter", 0.5),
                        "CCC": fake_run(run_id, "failed", "no compiling Java", 0.1)}[name]
        return run_id

    monkeypatch.setattr(deliver, "analyze", analyze)
    monkeypatch.setattr(deliver, "convert", convert)
    monkeypatch.setattr(deliver, "get_run", lambda rid: runs.get(rid))
    return tmp_path, calls


def record(tmp_path):
    return json.loads(next((tmp_path / "runs" / "deliveries").glob("*/delivery.json")).read_text())


def test_labels_reasons_and_costs_land_in_the_delivery_record(delivery_env, monkeypatch):
    tmp_path, calls = delivery_env
    monkeypatch.setenv("REPO_MAX_USD", "5")
    assert deliver.main(["https://github.com/o/r", "--convert-anyway"]) == 0
    d = record(tmp_path)
    jsonschema.validate(d, DELIVERY)
    by = {p["name"]: p for p in d["programs"]}
    assert d["convertAnyway"] and d["repoMaxUsd"] == 5 and d["spentUsd"] == pytest.approx(1.2)
    assert calls["analyze"] == [True]
    assert by["AAA"]["status"] == "certified" and by["AAA"]["assurance"] == "certified"
    # unverified programs are never "certified" in the record
    assert by["BBB"]["status"] == "not-certified" and by["BBB"]["assurance"] == "compiled-unverified"
    assert "EXEC SQL" in by["BBB"]["reason"] and by["BBB"]["costUsd"] == 0.5
    assert by["CCC"]["status"] == "not-certified" and by["CCC"]["assurance"] == "failed"
    assert all("--convert-anyway" in flags and convert is True for _, flags, convert in calls["convert"])


def test_repo_spend_cap_stops_the_run_with_a_stated_skip(delivery_env, monkeypatch):
    tmp_path, calls = delivery_env
    monkeypatch.setenv("REPO_MAX_USD", "1.00")  # AAA 0.6 + BBB 0.5 = 1.1 >= 1.00: CCC is skipped
    deliver.main(["https://github.com/o/r", "--convert-anyway"])
    d = record(tmp_path)
    jsonschema.validate(d, DELIVERY)
    ccc = next(p for p in d["programs"] if p["name"] == "CCC")
    assert ccc["status"] == "skipped" and "repo spend cap reached" in ccc["reason"] and ccc["runId"] is None
    assert [c[0] for c in calls["convert"]] == ["AAA", "BBB"]
    caps = [float(flags[flags.index("--max-usd") + 1]) for _, flags, _ in calls["convert"]]
    assert caps[0] == pytest.approx(1.0) and caps[1] == pytest.approx(0.4)  # each run gets only what is left


def test_default_cap_is_one_dollar_and_unknown_spend_fails_closed(monkeypatch):
    monkeypatch.delenv("REPO_MAX_USD", raising=False)
    s = deliver.Spend.from_env()
    assert s.cap == 1.00
    s.add(None)
    assert s.remaining() is None and "unknown" in s.reason()
    monkeypatch.setenv("REPO_MAX_USD", "nonsense")
    assert deliver.Spend.from_env().cap == 1.00


def test_without_the_flag_nothing_changes(delivery_env):
    tmp_path, calls = delivery_env
    deliver.main(["https://github.com/o/r"])
    assert calls["analyze"] == [False]
    assert [c[0] for c in calls["convert"]] == ["AAA", "CCC"]  # BBB stays refused
    assert all("--convert-anyway" not in flags and convert is False for _, flags, convert in calls["convert"])
    d = record(tmp_path)
    assert "convertAnyway" not in d and all("assurance" not in p for p in d["programs"])


# ---- visitors cannot turn it on ----------------------------------------------------------------

def test_public_delivery_refuses_the_flag_and_ignores_the_environment(delivery_env, monkeypatch):
    tmp_path, calls = delivery_env
    with pytest.raises(SystemExit):
        deliver.main(["https://github.com/o/r", "--public", "--convert-anyway"])
    monkeypatch.setenv("DIOCLE_CONVERT_ANYWAY", "1")  # set in the engine's environment
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    monkeypatch.setattr(deliver, "CompilePrecheck", lambda *a, **k: type("P", (), {"failure": lambda s, n: None, "record": lambda s: {}})())
    monkeypatch.setattr(deliver, "_visitor_caps", lambda programs, samples, pre=None: (programs, []))
    deliver.main(["https://github.com/o/r", "--public"])
    assert calls["analyze"] == [False]
    assert all(convert is False and "--convert-anyway" not in flags for _, flags, convert in calls["convert"])


def test_child_environment_strips_the_mode_unless_asked(monkeypatch):
    monkeypatch.setenv("DIOCLE_CONVERT_ANYWAY", "1")
    assert "DIOCLE_CONVERT_ANYWAY" not in deliver.child_env(False)
    assert deliver.child_env(True)["DIOCLE_CONVERT_ANYWAY"] == "1"


def test_visitor_http_request_cannot_enable_it(monkeypatch):
    monkeypatch.setenv("DIOCLE_ADMIN_TOKEN", "secret")
    monkeypatch.setenv("DIOCLE_PUBLIC_IMPORTS", "1")
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    started = []
    monkeypatch.setattr("diocle_api.app.start_delivery", lambda *a, **k: started.append((a, k)) or "delivery-x")
    c = TestClient(app)
    body = {"legacy": "https://github.com/o/r", "convertAnyway": True}
    assert c.post("/deliveries", json=body).status_code == 403
    assert c.post("/deliveries", json=body, headers={"X-Diocle-Admin": "wrong"}).status_code == 403
    assert started == []
    # a visitor request without the flag is still a normal visitor import, and never carries the mode
    monkeypatch.setattr("diocle_api.app.public.admit", lambda v: None)
    monkeypatch.setattr("diocle_api.app.running_delivery", lambda: None)
    assert c.post("/deliveries", json={"legacy": "https://github.com/o/r"}).status_code == 202
    assert started[-1][1].get("convert_anyway", False) is False and started[-1][1]["public"] is True
    # the admin may
    ok = c.post("/deliveries", json={**body, "target": "https://github.com/Nivetha200111/t"}, headers={"X-Diocle-Admin": "secret"})
    assert ok.status_code == 202 and started[-1][1]["convert_anyway"] is True


def test_start_delivery_never_passes_the_mode_to_a_public_job(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNS_DIR_UNUSED", "1")
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("DIOCLE_CONVERT_ANYWAY", "1")
    monkeypatch.setattr(deliveries, "running_delivery", lambda: None)
    with pytest.raises(ValueError):
        deliveries.start_delivery("https://github.com/o/r", None, False, False, public=True, convert_anyway=True)
    seen = {}
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: seen.update(cmd=cmd, env=kw["env"]) or None)
    deliveries.start_delivery("https://github.com/o/r", None, False, False, public=True)
    assert "DIOCLE_CONVERT_ANYWAY" not in seen["env"] and "--convert-anyway" not in seen["cmd"]


# ---- pull request wording ----------------------------------------------------------------------

def test_pr_body_lists_every_program_with_its_label_and_a_clear_sentence():
    cert = {"program": "AAA", "verification": {"passed": 9, "total": 9, "stdoutMatch": True},
            "agent": {"modelCalls": 1, "rounds": 1, "memoryLessonsUsed": 0, "estimatedCostUsd": 0.01}}
    others = [
        {"name": "BBB", "assurance": "compiled-unverified",
         "reason": deliver.unverified_sentence("compiled-unverified", "EXEC SQL needs a database adapter")},
        {"name": "DDD", "assurance": "certified-against-repaired-cobol",
         "reason": "The original did not compile under GnuCOBOL. Muse changed 1 line(s) (diff in the run record) so it compiles; "
                   "the Java was verified against the patched COBOL, not the original. A person must confirm the patch preserves "
                   "what the IBM compiler accepted."},
        {"name": "CCC", "assurance": "failed", "reason": "no compiling Java within the caps"}]
    body = deliver._pr_body({"source": SRC}, [({}, cert)], ["EEE"], others)
    certified_part, rest = body.split("## Verified against repaired COBOL")
    assert "`AAA`" in certified_part and "`BBB`" not in certified_part and "`DDD`" not in certified_part
    assert "## Compiled, NOT verified" in rest and "Java compiles; a developer must review it; the differential test could not run because EXEC SQL" in rest
    assert "not the original" in rest and "A person must confirm" in rest and "## Failed (not delivered)" in rest
    assert "`CCC`" in rest and "`EEE`" in rest
    section = body.split("## Compiled, NOT verified")[1].split("## Failed")[0].lower()
    assert "certified" not in section.replace("not certified", "")  # nothing implies unverified code is proven


def test_pr_body_with_nothing_certified_does_not_claim_it():
    body = deliver._pr_body({"source": SRC}, [], [], [{"name": "BBB", "assurance": "compiled-unverified", "reason": "r"}])
    assert "No program below is certified" in body and "nothing here is certified" in body
    assert "reverify" not in body and "certified by [Diocle]" not in body


def test_other_programs_reads_labels_from_run_records(monkeypatch):
    runs = {"r1": fake_run("r1", "compiled-unverified", "x", 0.1), "r2": fake_run("r2", "certified", None, 0.1, certified=True),
            "r3": {**fake_run("r3", None, None, 0.1), "assurance": None}}
    monkeypatch.setattr(deliver, "get_run", runs.get)
    report = {"programs": [{"name": n} for n in ("A", "B", "C", "D")]}
    out = deliver._other_programs(report, {"A": "r1", "B": "r2", "C": "r3"})
    assert [o["name"] for o in out] == ["A"]


# ---- contracts ---------------------------------------------------------------------------------

def test_run_contract_accepts_labels_and_old_runs_and_rejects_unknown_ones():
    base = {"id": "r", "program": "P", "command": "run", "certified": False, "javaOrigin": "x", "events": [], "usage": {"calls": 0, "inputTokens": 0, "outputTokens": 0}}
    jsonschema.validate(base, RUN)  # an old run: no assurance fields
    for label in ("certified", "certified-against-repaired-cobol", "compiled-unverified", "failed"):
        jsonschema.validate({**base, "assurance": label, "assuranceReason": "why"}, RUN)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**base, "assurance": "mostly-certified"}, RUN)
    repair = {"method": "deterministic", "outcome": "compiles", "diff": "", "diagnostics": [], "changedLines": 1}
    jsonschema.validate({**base, "assurance": "certified-against-repaired-cobol", "cobolRepair": repair}, RUN)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**base, "cobolRepair": {**repair, "method": "magic"}}, RUN)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**base, "cobolRepair": {"method": "model"}}, RUN)


def test_delivery_contract_old_records_stay_valid_and_bad_labels_are_rejected():
    old = {"id": "d", "legacy": {"repository": "u"}, "target": None, "stage": "done", "startedAt": "t",
           "programs": [{"name": "A", "status": "certified"}]}
    jsonschema.validate(old, DELIVERY)
    jsonschema.validate({**old, "convertAnyway": True, "repoMaxUsd": 1.0, "spentUsd": 0.2,
                         "programs": [{"name": "A", "status": "not-certified", "assurance": "compiled-unverified", "reason": "r",
                                       "costUsd": 0.1}]}, DELIVERY)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({**old, "programs": [{"name": "A", "status": "certified", "assurance": "proven"}]}, DELIVERY)


def test_get_run_exposes_the_labels_only_when_present(tmp_path, monkeypatch):
    from diocle_api import runs

    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    d = tmp_path / "p-20261030-000000"
    d.mkdir()
    (d / "run.json").write_text(json.dumps({"program": "P", "command": "run", "certified": False, "status": "not-certified",
                                            "assurance": "compiled-unverified", "assuranceReason": "r", "usage": {"calls": 0, "inputTokens": 0, "outputTokens": 0}}))
    run = runs.get_run(d.name)
    assert run["assurance"] == "compiled-unverified" and run["certified"] is False
    jsonschema.validate(run, RUN)
    assert runs.list_runs()[0]["assurance"] == "compiled-unverified"
    (d / "run.json").write_text(json.dumps({"program": "P", "command": "run", "certified": True, "usage": {}}))
    assert "assurance" not in runs.get_run(d.name) and "assurance" not in runs.list_runs()[0]
