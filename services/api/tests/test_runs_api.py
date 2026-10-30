import json
from datetime import datetime, timezone
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from diocle_api.app import app

CONTRACT_DIR = Path(__file__).resolve().parents[3] / "contracts"
CONTRACT = json.loads((CONTRACT_DIR / "run.schema.json").read_text())


def _report(passed: int, total: int) -> dict:
    results = [{"program": "P", "inputId": f"case-{i}", "match": i < passed, "inputSource": "random",
                "fieldDiffs": [] if i < passed else [{"field": "OUT-FEE", "original": "1.49", "converted": "1.50"}],
                **({} if i < passed else {"diff": "OUT-FEE: original 1.49 converted 1.50"})} for i in range(total)]
    side = {"compiled": True, "exitCode": 0, "stdout": "", "stderr": ""}
    return {"version": "0.2", "results": results, "summary": {"total": total, "passed": passed, "failed": total - passed},
            "runs": {"original": side, "converted": side, "stdoutMatch": passed == total}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    run = tmp_path / "demo-20261028-124509"
    (run / "java").mkdir(parents=True)
    (run / "java" / "A.java").write_text("class A {}\n")
    sample = tmp_path / "samples" / "demo"
    (sample / "copybooks").mkdir(parents=True)
    (sample / "sample.json").write_text(json.dumps({"source": "DEMO.cbl", "copybookDir": "copybooks"}))
    (sample / "DEMO.cbl").write_text("       IDENTIFICATION DIVISION.\n      * a comment\n\n       PROGRAM-ID. DEMO.\n")
    (sample / "copybooks" / "REC.cpy").write_text("       01 REC PIC X.\n")
    (run / "run.json").write_text(json.dumps({
        "program": "DEMO", "command": "run", "sample": str(sample), "javaOrigin": "translated by muse-spark-1.3-contributor", "certified": True,
        "rounds": [{"round": 1, "certified": True}],
        "memory": {"enabled": True, "used": 2, "learned": 1,
                   "lessons": [{"pattern": "ROUNDED ties", "cobol": "half away from zero", "java": "HALF_UP"}]},
        "usage": {"calls": 2, "inputTokens": 10, "cachedInputTokens": 4, "outputTokens": 5, "estimatedCostUsd": 0.001,
                  "modelCalls": [{"model": "muse-spark-1.3-contributor"}]}}))
    (run / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in [
        {"type": "agent-step", "round": 1, "step": 1, "tool": "patch_java", "rationale": "", "argsSummary": {},
         "resultSummary": "applied. Lines 1-2 now read:"},
        {"type": "agent-step", "round": 1, "step": 2, "tool": "patch_java", "rationale": "", "argsSummary": {},
         "resultSummary": "rejected: old_text not found"},
        {"type": "agent-step", "round": 1, "step": 3, "tool": "compile_java", "rationale": "", "argsSummary": {},
         "resultSummary": "compiled OK"}]))
    (run / "initial-verification.json").write_text(json.dumps(_report(3, 5)))
    (run / "verification-report.json").write_text(json.dumps(_report(5, 5)))
    (tmp_path / "not-a-run").mkdir()
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    return TestClient(app)


def test_lists_runs(client):
    runs = client.get("/runs").json()
    assert [r["id"] for r in runs] == ["demo-20261028-124509"]
    assert runs[0]["certified"] and runs[0]["calls"] == 2 and runs[0]["createdAt"] == "2026-10-28T12:45:09"


def test_run_detail_matches_contract(client):
    run = client.get("/runs/demo-20261028-124509").json()
    jsonschema.validate(run, CONTRACT)
    assert run["before"]["failed"] == 2 and run["before"]["failingExamples"][0]["inputId"] == "case-3"
    assert run["after"]["failed"] == 0 and run["model"] == "muse-spark-1.3-contributor"
    assert run["javaDiff"] is None  # translated runs have no starting file to diff against


def test_database_comparison_passthrough(client, tmp_path):
    run = tmp_path / "demo-20261028-124509"
    assert "database" not in client.get("/runs/demo-20261028-124509").json()["after"]
    report = _report(5, 5)
    report["runs"]["database"] = {"engine": "sqlite", "engineVersion": "3.45.0", "subset": "db2-subset-1", "seededFrom": "schema.sql",
                                  "tables": [{"name": "T", "rowsSeeded": 2, "rowsOriginal": 3, "rowsConverted": 3, "match": True,
                                              "firstMismatch": None, "changedFromSeed": {"original": True, "converted": True}}]}
    (run / "verification-report.json").write_text(json.dumps(report))
    after = client.get("/runs/demo-20261028-124509").json()
    jsonschema.validate(after, CONTRACT)
    assert after["after"]["database"] == report["runs"]["database"]


def test_rejects_unknown_and_unsafe_ids(client):
    assert client.get("/runs/missing-run").status_code == 404
    assert client.get("/runs/..%2F..%2Fetc").status_code == 404
    assert client.get("/runs/not-a-run").status_code == 404


def test_efficiency(client):
    eff = client.get("/runs/demo-20261028-124509").json()["efficiency"]
    assert eff["cobolLines"] == 3  # comment and blank lines are not counted
    assert eff["modelCalls"] == 2 and eff["toolSteps"] == 3 and eff["patchesApplied"] == 1
    assert eff["cacheHitRate"] == 0.4 and eff["totalTokens"] == 15
    assert eff["costPer1kLinesUsd"] == pytest.approx(0.001 / 3 * 1000, abs=1e-6)
    assert client.get("/runs").json()[0]["efficiency"] == eff
    run = client.get("/runs/demo-20261028-124509").json()
    assert run["memory"]["used"] == 2 and run["memory"]["lessons"][0]["java"] == "HALF_UP"


def test_running_run_and_delivery_progress(client, tmp_path, monkeypatch):
    live = tmp_path / "live-20261028-180000"
    live.mkdir()
    (live / "run.json").write_text(json.dumps({"program": "LIVE", "command": "run", "status": "running", "certified": False,
                                               "rounds": [], "usage": {"calls": 1, "inputTokens": 5, "outputTokens": 1}}))
    (live / "events.jsonl").write_text(json.dumps({"type": "stage", "stage": "repairing", "message": "m"}) + "\n")
    delivery = tmp_path / "deliveries" / "delivery-20261028-180000"
    delivery.mkdir(parents=True)
    (delivery / "delivery.json").write_text(json.dumps({
        "id": "delivery-20261028-180000", "legacy": {"repository": "https://github.com/o/legacy", "commit": "abc"},
        "target": "https://github.com/o/modern", "stage": "converting", "startedAt": "2026-10-28T12:30:00+00:00",
        "finishedAt": None, "error": None, "pullRequest": None,
        "programs": [{"name": "LIVE", "status": "converting", "runId": "live-20261028-180000"},
                     {"name": "NEXT", "status": "queued", "runId": None}]}))
    run = client.get("/runs/live-20261028-180000").json()
    jsonschema.validate(run, CONTRACT)
    assert run["status"] == "running" and run["after"] is None
    d = client.get("/deliveries/delivery-20261028-180000").json()
    jsonschema.validate(d, json.loads((CONTRACT_DIR / "delivery.schema.json").read_text()))
    assert d["programs"][0]["run"]["stage"] == "repairing" and d["programs"][1]["run"] is None
    assert client.get("/deliveries").json()[0]["programs"] == 2
    assert client.get("/deliveries/..%2Fx").status_code == 404


def test_polling_survives_files_caught_mid_write(client, tmp_path):
    half = tmp_path / "half-20261028-190000"
    half.mkdir()
    (half / "run.json").write_text('{"program": "HALF", "comm')
    assert client.get("/runs/half-20261028-190000").status_code == 404
    assert "half-20261028-190000" not in [r["id"] for r in client.get("/runs").json()]
    live = tmp_path / "demo-20261028-124509"
    with (live / "events.jsonl").open("a") as f:
        f.write('{"type": "agent-st')  # partial line from a live run
    assert client.get("/runs/demo-20261028-124509").status_code == 200


def test_dot_ids_are_rejected(client, tmp_path):
    (tmp_path / "delivery.json").write_text("{}")
    from diocle_api.deliveries import get_delivery
    from diocle_api.runs import get_run
    for bad in ("..", ".", ".hidden"):  # checked directly: HTTP clients normalise dot segments before sending
        assert get_delivery(bad) is None and get_run(bad) is None
    assert client.get("/runs/%2E%2E").status_code == 404


def test_start_delivery_validates_and_allows_one_at_a_time(client, tmp_path, monkeypatch):
    import diocle_api.deliveries as d
    started = []
    monkeypatch.setattr(d.subprocess, "Popen", lambda cmd, **kw: started.append(cmd))
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    bad = client.post("/deliveries", json={"legacy": "https://github.com/x/y", "target": "https://evil.example/repo"})
    assert bad.status_code == 400 and not started
    other = client.post("/deliveries", json={"legacy": "https://github.com/Nivetha200111/a",
                                              "target": "https://github.com/someone-else/b"})
    assert other.status_code == 400 and not started
    ok = client.post("/deliveries", json={"legacy": "https://github.com/Nivetha200111/a",
                                           "target": "https://github.com/Nivetha200111/b", "breaker": True})
    assert ok.status_code == 202 and ok.json()["id"].startswith("delivery-")
    assert started[0][-2:] == ["--id", ok.json()["id"]] or "--breaker" in started[0]
    running = tmp_path / "deliveries" / ok.json()["id"]
    (running / "delivery.json").write_text(json.dumps({
        "id": ok.json()["id"], "legacy": {"repository": "a", "commit": None}, "target": "b", "stage": "converting",
        "startedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "finishedAt": None, "programs": [],
        "pullRequest": None}))  # just started, no pid yet: counts as running. (A fixed old time made the 409 come from
    # the same-second id check instead, so the test passed or failed with the clock.)
    busy = client.post("/deliveries", json={"legacy": "https://github.com/Nivetha200111/a",
                                             "target": "https://github.com/Nivetha200111/b"})
    assert busy.status_code == 409 and "still running" in busy.json()["detail"] and len(started) == 1


def test_admin_passcode_guards_starting(client, monkeypatch):
    import diocle_api.deliveries as d
    monkeypatch.setattr(d.subprocess, "Popen", lambda cmd, **kw: None)
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    body = {"legacy": "https://github.com/Nivetha200111/a", "target": "https://github.com/Nivetha200111/b"}
    monkeypatch.setenv("DIOCLE_HOSTED", "1")
    monkeypatch.delenv("DIOCLE_ADMIN_TOKEN", raising=False)
    assert client.post("/deliveries", json=body).status_code == 403  # hosted without a token: never
    config = client.get("/config").json()
    assert (config["hosted"], config["startNeedsPasscode"], config["publicImports"]["enabled"]) == (True, True, False)
    monkeypatch.setenv("DIOCLE_ADMIN_TOKEN", "s3cret-passcode")
    assert client.post("/deliveries", json=body, headers={"X-Diocle-Admin": "wrong"}).status_code == 403
    assert client.post("/deliveries", json=body, headers={"X-Diocle-Admin": "s3cret-passcode"}).status_code == 202


def test_visitor_imports_need_the_sandbox_and_respect_limits(client, monkeypatch):
    import diocle_api.deliveries as d
    import diocle_api.public as public
    started = []
    monkeypatch.setattr(d.subprocess, "Popen", lambda cmd, **kw: started.append((cmd, kw["env"])))
    monkeypatch.setattr(d, "running_delivery", lambda: None)
    monkeypatch.setattr("diocle_api.app.running_delivery", lambda: None)
    monkeypatch.setattr(public, "_seen", {})
    monkeypatch.setenv("DIOCLE_HOSTED", "1")
    monkeypatch.setenv("DIOCLE_ADMIN_TOKEN", "s3cret-passcode")
    monkeypatch.setenv("GH_TOKEN", "must-not-reach-visitor-runs")
    body = {"legacy": "https://github.com/someone-else/cobol-estate"}
    monkeypatch.setenv("DIOCLE_PUBLIC_IMPORTS", "1")
    monkeypatch.delenv("DIOCLE_SANDBOX_URL", raising=False)
    assert client.post("/deliveries", json=body).status_code == 403  # no sandbox, no visitor imports
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox:8100")
    monkeypatch.setenv("DIOCLE_PUBLIC_PER_VISITOR", "2")
    monkeypatch.setattr(public, "spent_today", lambda: 0.0)
    visitor = {"x-vercel-forwarded-for": "203.0.113.7"}
    assert client.post("/deliveries", json=body, headers=visitor).status_code == 202
    cmd, env = started[-1]
    assert "--public" in cmd and "https://github.com/someone-else/cobol-estate" in cmd and len(cmd) == 7
    assert env["DIOCLE_IMPORT_ANY"] == "1" and "GH_TOKEN" not in env
    import shutil
    from diocle_api.runs import runs_dir
    fresh = lambda: shutil.rmtree(runs_dir() / "deliveries", ignore_errors=True)  # noqa: E731 (one start per second)
    fresh()
    n = len(started)
    assert client.post("/deliveries", json={**body, "target": "https://github.com/someone-else/x"},
                       headers=visitor).status_code == 403  # a visitor's target is refused (it used to be ignored), never delivered to
    assert len(started) == n
    assert client.post("/deliveries", json=body, headers=visitor).status_code == 202  # still a normal import
    fresh()
    assert client.post("/deliveries", json=body, headers=visitor).status_code == 429  # per-visitor limit
    monkeypatch.setattr(public, "spent_today", lambda: 5.0)
    other = {"x-vercel-forwarded-for": "198.51.100.9"}
    assert client.post("/deliveries", json=body, headers=other).status_code == 429  # daily budget
    assert client.post("/deliveries", json=body, headers={"X-Diocle-Admin": "wrong"}).status_code == 403


@pytest.fixture
def samples_here(tmp_path, monkeypatch):
    """The fixture's sample lives in the temp runs dir, outside the real sample roots."""
    import diocle_api.runs as runs
    monkeypatch.setattr(runs, "_sample_roots", lambda: [(tmp_path / "samples").resolve()])


def _visitor_run(tmp_path, run_id: str, public: bool) -> None:
    delivery = tmp_path / "deliveries" / "delivery-20261028-170821"
    sample = delivery / "samples" / "acct"
    sample.mkdir(parents=True)
    (delivery / "delivery.json").write_text(json.dumps({"id": delivery.name, "public": public}))
    (sample / "sample.json").write_text(json.dumps({"source": "ACCT.cbl"}))
    (sample / "ACCT.cbl").write_text("       PROGRAM-ID. ACCT.\n")
    (tmp_path / run_id / "java").mkdir(parents=True)
    (tmp_path / run_id / "java" / "Acct.java").write_text("class Acct {}\n")
    (tmp_path / run_id / "run.json").write_text(json.dumps({
        "program": "ACCT", "command": "run", "sample": str(sample), "certified": True, "rounds": [], "usage": {}}))


def test_a_visitor_run_without_its_marker_is_still_a_visitor_run(client, tmp_path):
    # Runs saved before the marker existed, or read before the delivery writes it, are found by their sample.
    _visitor_run(tmp_path, "acct-20261028-170822", public=True)
    assert client.get("/runs/acct-20261028-170822").json()["visitor"] is True
    assert client.get("/runs/acct-20261028-170822/source").status_code == 404
    assert client.post("/runs/acct-20261028-170822/reverify").status_code == 400


def test_an_admin_delivery_run_is_not_a_visitor_run(client, tmp_path):
    _visitor_run(tmp_path, "acct-20261028-194951", public=False)
    assert client.get("/runs/acct-20261028-194951").json()["visitor"] is False
    source = client.get("/runs/acct-20261028-194951/source").json()
    assert [f["path"] for f in source["cobol"]] == ["ACCT.cbl"] and source["java"][0]["path"] == "Acct.java"


def test_a_silent_running_run_reads_as_interrupted(client, tmp_path):
    import os
    import time
    run = tmp_path / "demo-20261028-124509"
    meta = json.loads((run / "run.json").read_text())
    (run / "run.json").write_text(json.dumps({**meta, "status": "running", "certified": False}))
    assert client.get("/runs").json()[0]["status"] == "running"
    old = time.time() - 31 * 60
    for f in ("run.json", "events.jsonl"):
        os.utime(run / f, (old, old))
    assert client.get("/runs").json()[0]["status"] == "interrupted"
    jsonschema.validate(client.get("/runs/demo-20261028-124509").json(), CONTRACT)


def test_source_survives_a_broken_sample(client, tmp_path, samples_here):
    (tmp_path / "samples" / "demo" / "sample.json").write_text("{not json")
    source = client.get("/runs/demo-20261028-124509/source")
    assert source.status_code == 200 and source.json()["cobol"] == [] and source.json()["java"]


def test_source_serves_cobol_next_to_java(client, tmp_path, samples_here):
    source = client.get("/runs/demo-20261028-124509/source").json()
    jsonschema.validate(source, {"$ref": "#/$defs/source", "$defs": CONTRACT["$defs"]})
    assert [f["path"] for f in source["cobol"]] == ["DEMO.cbl", "copybooks/REC.cpy"]
    assert [(f["path"], f["text"].strip(), f["truncated"]) for f in source["java"]] == [("A.java", "class A {}", False)]
    assert client.get("/runs/missing-run/source").status_code == 404
    assert client.get("/runs/..%2F..%2Fetc/source").status_code == 404
    (tmp_path / "demo-20261028-124509" / "visitor").write_text("")
    assert client.get("/runs/demo-20261028-124509/source").status_code == 404  # visitor code is not served


def test_source_skips_files_outside_the_sample_and_the_run(client, tmp_path, samples_here):
    import os
    secret = tmp_path.parent / f"{tmp_path.name}-secret.txt"
    secret.write_text("SECRET")
    try:
        os.symlink(secret, tmp_path / "demo-20261028-124509" / "java" / "Leak.java")
    except OSError:
        pytest.skip("symlinks need extra privileges on this machine")
    source = client.get("/runs/demo-20261028-124509/source").json()
    assert all("SECRET" not in f["text"] for f in source["java"] + source["cobol"])


def test_reverify_runs_only_certified_runs_with_samples(client):
    assert client.post("/runs/missing-run/reverify").status_code == 404
    assert client.post("/runs/demo-20261028-124509/reverify").status_code == 502  # its sample has no real COBOL


def test_reverify_a_real_certified_run():
    import pytest
    from diocle_api.reverify import reverify_run
    from diocle_api.runs import list_runs
    # a run certified under the current oracle (runs named intaccr-* come from the IBM TRUNC/DISPLAY verifier)
    real = next((r for r in list_runs() if r["certified"] and r["id"].startswith("intaccr-")), None)
    if real is None:
        pytest.skip("no certified INTACCR run on this machine")
    result = reverify_run(real["id"], cases=100)
    assert result["allMatch"] and result["total"] >= 100 and result["seed"] >= 10**6


def test_a_new_delivery_blocks_the_next_start_and_a_dead_one_does_not(client, monkeypatch):
    import json as _json
    from datetime import datetime, timedelta, timezone

    import diocle_api.deliveries as d
    from diocle_api.runs import runs_dir
    monkeypatch.setattr(d.subprocess, "Popen", lambda cmd, **kw: None)
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    monkeypatch.delenv("DIOCLE_HOSTED", raising=False)
    monkeypatch.delenv("DIOCLE_ADMIN_TOKEN", raising=False)
    body = {"legacy": "https://github.com/Nivetha200111/a", "target": "https://github.com/Nivetha200111/b"}
    first = client.post("/deliveries", json=body).json()["id"]
    record = _json.loads((runs_dir() / "deliveries" / first / "delivery.json").read_text())
    assert record["stage"] == "analyzing"  # written before the response
    assert client.post("/deliveries", json=body).status_code == 409  # it counts as running straight away
    # Ten minutes later with no live process (the engine restarted): marked failed, starts are possible again.
    old = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(timespec="seconds")
    (runs_dir() / "deliveries" / first / "delivery.json").write_text(_json.dumps({**record, "startedAt": old}))
    assert d.running_delivery() is None
    assert _json.loads((runs_dir() / "deliveries" / first / "delivery.json").read_text())["stage"] == "failed"


def test_visitor_budget_counts_24_hours_and_fails_closed_on_unknown_cost(tmp_path, monkeypatch):
    import diocle_api.public as public
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    for name, usage in (("a-20261028-100000", {"calls": 4, "estimatedCostUsd": 0.02}),
                        ("b-20261028-110000", {"calls": 0, "estimatedCostUsd": None})):
        (tmp_path / name).mkdir()
        (tmp_path / name / "run.json").write_text(json.dumps({"usage": usage}))
    assert public.spent_today() == 0.02
    (tmp_path / "c-20261028-120000").mkdir()
    (tmp_path / "c-20261028-120000" / "run.json").write_text(json.dumps({"usage": {"calls": 3, "estimatedCostUsd": None}}))
    assert public.spent_today() == float("inf") and public.status()["budgetLeft"] is False


def test_requests_from_the_sandbox_are_refused(client, monkeypatch):
    import diocle_api.app as app_module
    monkeypatch.setattr(app_module, "_sandbox", lambda: {"testclient"})
    assert client.get("/health").status_code == 403
    monkeypatch.setattr(app_module, "_sandbox", lambda: {"10.9.9.9"})
    assert client.get("/health").status_code == 200


def test_visitor_runs_are_labelled_and_not_reverified(client):
    from diocle_api.reverify import reverify_run
    from diocle_api.runs import list_runs, runs_dir
    (runs_dir() / "demo-20261028-124509" / "visitor").write_text("delivery-x\n")
    assert next(r for r in list_runs() if r["id"] == "demo-20261028-124509")["visitor"] is True
    import pytest
    with pytest.raises(ValueError, match="visitor"):
        reverify_run("demo-20261028-124509")


def test_schema_serves_tables_and_the_round_trip_proof(client, tmp_path, samples_here):
    import diocle_api.schema as schema

    schema._cache.clear()
    sample = tmp_path / "samples" / "demo"
    layout = {"record": "REC", "fields": [{"name": "REC-ID", "kind": "alnum", "length": 4},
                                          {"name": "REC-AMT", "kind": "numeric", "digits": 5, "scale": 2, "signed": True,
                                           "usage": "packed"}], "format": "fixed"}
    (sample / "sample.json").write_text(json.dumps({"source": "DEMO.cbl", "program": "DEMO", "dd": {"input": "IN", "output": "OUT"},
                                                    "layouts": {"input": layout, "output": layout}}))
    got = client.get("/runs/demo-20261028-124509/schema")
    assert got.status_code == 200
    body = got.json()
    jsonschema.validate(body, json.loads((CONTRACT_DIR / "sql-schema.schema.json").read_text()))
    assert body["runId"] == "demo-20261028-124509" and body["summary"]["passed"]
    assert [t["table"] for t in body["tables"]] == ["rec", "rec_out"]
    assert '"rec_amt" DECIMAL(7,2) NOT NULL' in body["ddl"]
    assert client.get("/runs/missing-run/schema").status_code == 404
    assert client.get("/runs/..%2F..%2Fetc/schema").status_code == 404
    (tmp_path / "demo-20261028-124509" / "visitor").write_text("")
    assert client.get("/runs/demo-20261028-124509/schema").status_code == 404  # visitor layouts are not served


def test_schema_is_404_without_a_readable_sample(client, tmp_path, samples_here):
    import diocle_api.schema as schema

    schema._cache.clear()
    (tmp_path / "samples" / "demo" / "sample.json").write_text("{not json")
    assert client.get("/runs/demo-20261028-124509/schema").status_code == 404


def test_schema_failures_are_not_cached(client, tmp_path, samples_here, monkeypatch):
    import diocle_api.schema as schema

    schema._cache.clear()
    sample = tmp_path / "samples" / "demo"
    (sample / "sample.json").write_text("{not json")
    assert client.get("/runs/demo-20261028-124509/schema").status_code == 404
    layout = {"record": "REC", "fields": [{"name": "REC-ID", "kind": "alnum", "length": 4}]}
    (sample / "sample.json").write_text(json.dumps({"source": "DEMO.cbl", "dd": {"input": "IN", "output": "OUT"},
                                                    "layouts": {"input": layout, "output": layout}}))
    assert client.get("/runs/demo-20261028-124509/schema").status_code == 200  # fixed sample: computed again


def test_schema_is_withheld_for_a_public_delivery_sample(client, tmp_path, monkeypatch):
    import diocle_api.runs as runs

    monkeypatch.setattr(runs, "_sample_roots", lambda: [(tmp_path / "deliveries").resolve()])
    _visitor_run(tmp_path, "acct-20261028-171000", public=True)
    assert client.get("/runs/acct-20261028-171000/schema").status_code == 404


def test_crosscheck_result_is_passed_through_and_matches_the_contract(client, tmp_path):
    path = tmp_path / "demo-20261028-124509" / "run.json"
    run = json.loads(path.read_text())
    run["crosscheck"] = {"model": "accounts/fireworks/models/muse-spark-open", "casesProposed": 15, "casesValid": 12,
                         "mismatches": 0, "repairCycles": 0, "fixed": False,
                         "suspected": [{"field": "OUT-FEE", "concern": "rounding"}], "counterexamples": []}
    path.write_text(json.dumps(run))
    body = client.get("/runs/demo-20261028-124509").json()
    jsonschema.validate(body, CONTRACT)
    assert body["crosscheck"]["casesValid"] == 12
    run["crosscheck"] = {"skipped": "no CROSSCHECK_MODEL_* or OPEN_MODEL_* configured"}
    path.write_text(json.dumps(run))
    jsonschema.validate(client.get("/runs/demo-20261028-124509").json(), CONTRACT)


def test_behavior_claims_are_passed_through_and_match_the_contracts(client, tmp_path):
    path = tmp_path / "demo-20261028-124509" / "run.json"
    run = json.loads(path.read_text())
    assert client.get("/runs/demo-20261028-124509").json()["behavior"] is None  # old runs stay valid
    behavior = {"version": "0.1", "program": "INTACCR", "model": "muse-spark-1.3-contributor", "checkedWith": "GnuCOBOL -std=ibm",
                "summary": {"claims": 1, "confirmed": 0, "refuted": 1, "unchecked": 0, "examplesRun": 1},
                "claims": [{"id": "C1", "statement": "A tie rounds toward zero.", "status": "refuted", "examples": [{
                    "id": "C1-E1", "inputs": [{"ACCT-ID": "X"}], "expected": {"records": [{"OUT-INTEREST": "0.00"}]},
                    "status": "differed", "actual": {"records": [{"OUT-INTEREST": "0.01"}], "outputRecordCount": 1},
                    "mismatches": [{"what": "record 1 OUT-INTEREST", "expected": "0.00", "actual": "0.01"}]}]}]}
    jsonschema.validate(behavior, json.loads((CONTRACT_DIR / "behavior-claims.schema.json").read_text()))
    run["behavior"] = behavior
    path.write_text(json.dumps(run))
    with (tmp_path / "demo-20261028-124509" / "events.jsonl").open("a") as f:
        f.write(json.dumps({"type": "behavior", "message": "Verified documentation: 0 of 1 claims confirmed"}) + "\n")
    body = client.get("/runs/demo-20261028-124509").json()
    jsonschema.validate(body, CONTRACT)
    assert body["behavior"]["claims"][0]["status"] == "refuted" and body["events"][-1]["type"] == "behavior"


def test_run_detail_carries_the_guard_result(client, tmp_path):
    run_json = tmp_path / "demo-20261028-124509" / "run.json"
    run = json.loads(run_json.read_text())
    finding = {"severity": "block", "category": "test-gaming", "file": "A.java", "line": 7,
               "explanation": "returns 20.00 for one account ID the COBOL never mentions"}
    run["guard"] = {"blocked": True, "stopped": 0, "policy": [], "sourceFlags": [],
                    "review": {"model": "meta-models/muse-spark-open-1026", "verdict": "block", "summary": "s",
                               "findings": [finding]}}
    run_json.write_text(json.dumps(run))
    with (tmp_path / "demo-20261028-124509" / "events.jsonl").open("a") as f:
        f.write(json.dumps({"type": "guard", "blocked": True, "message": "Guard review: BLOCK"}) + "\n")
    got = client.get("/runs/demo-20261028-124509").json()
    jsonschema.validate(got, CONTRACT)
    assert got["guard"]["review"]["findings"] == [finding] and got["events"][-1]["type"] == "guard"


def test_the_guard_model_does_not_become_the_run_model(client, tmp_path):
    run_json = tmp_path / "demo-20261028-124509" / "run.json"
    run = json.loads(run_json.read_text())
    run["usage"]["modelCalls"] = [{"role": "guard", "model": "meta-models/muse-spark-open-1026"}]
    run_json.write_text(json.dumps(run))
    assert client.get("/runs/demo-20261028-124509").json()["model"] is None
    run["usage"]["modelCalls"].append({"role": "repair", "model": "muse-spark-1.3-contributor"})
    run_json.write_text(json.dumps(run))
    assert client.get("/runs").json()[0]["model"] == "muse-spark-1.3-contributor"


def test_tiers_result_is_passed_through_and_matches_the_contract(client, tmp_path):
    path = tmp_path / "demo-20261028-124509" / "run.json"
    run = json.loads(path.read_text())
    run["tiers"] = {"enabled": True, "configured": ["muse-spark-1.3-contributor", "muse-spark-1.3", "muse-wonder-1.0"],
                    "escalations": [{"round": 2, "tier": 2, "model": "muse-spark-1.3"}],
                    "breakerModel": "muse-wonder-1.0", "escalatedCalls": 3, "escalatedUsd": 0.021,
                    "capCalls": 12, "capUsd": 0.5}
    path.write_text(json.dumps(run))
    body = client.get("/runs/demo-20261028-124509").json()
    jsonschema.validate(body, CONTRACT)
    assert body["tiers"]["escalations"][0]["model"] == "muse-spark-1.3"
    assert body["model"] == "muse-spark-1.3-contributor"  # escalation never renames the run's default model
