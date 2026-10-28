import json
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
        "startedAt": "2026-10-28T12:30:00+00:00", "finishedAt": None, "programs": [], "pullRequest": None}))
    busy = client.post("/deliveries", json={"legacy": "https://github.com/Nivetha200111/a",
                                             "target": "https://github.com/Nivetha200111/b"})
    assert busy.status_code == 409 and len(started) == 1
