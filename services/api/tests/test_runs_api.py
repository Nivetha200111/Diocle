import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from diocle_api.app import app

CONTRACT = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "run.schema.json").read_text())


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
