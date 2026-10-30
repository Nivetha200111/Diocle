import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import diocle_api.mutation as mutation
from diocle_api.app import app

RUN = "demo-20261030-100000"
VALID = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "examples" / "mutation-report.valid.json").read_text())


@pytest.fixture
def client(tmp_path, monkeypatch):
    sample = tmp_path / "samples" / "demo"
    sample.mkdir(parents=True)
    (sample / "sample.json").write_text("{}")
    run = tmp_path / RUN
    (run / "java").mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"program": "DEMO", "sample": str(sample), "certified": True}))
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(mutation, "_last_finished", 0.0)
    return TestClient(app)


def fake_cli(monkeypatch, report=None, calls=None):
    def run(cmd, **kw):
        if calls is not None:
            calls.append(cmd)
        if report is not None:
            Path(cmd[-1], "mutation-report.json").write_text(json.dumps(report))
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(mutation.subprocess, "run", run)


def test_get_is_404_until_a_report_exists_then_serves_it(client, tmp_path):
    assert client.get(f"/runs/{RUN}/mutation").status_code == 404
    (tmp_path / RUN / "mutation-report.json").write_text(json.dumps(VALID))
    assert client.get(f"/runs/{RUN}/mutation").json()["counts"]["killed"] == 3
    (tmp_path / RUN / "mutation-report.json").write_text("not json")
    assert client.get(f"/runs/{RUN}/mutation").status_code == 404
    assert client.get("/runs/..%2Fetc/mutation").status_code == 404


def test_post_runs_the_cli_on_the_run_and_returns_its_report(client, monkeypatch):
    calls: list = []
    fake_cli(monkeypatch, {**VALID, "runId": RUN}, calls)
    body = client.post(f"/runs/{RUN}/mutation").json()
    assert body["runId"] == RUN and calls[0][-3:-1] == ["diocle_verifier", "mutate"] and calls[0][-1].endswith(RUN)


def test_post_is_gated_like_reverify(client, tmp_path, monkeypatch):
    fake_cli(monkeypatch, {**VALID, "runId": RUN})
    assert client.post("/runs/missing-run/mutation").status_code == 404
    run_json = tmp_path / RUN / "run.json"
    meta = json.loads(run_json.read_text())
    run_json.write_text(json.dumps({**meta, "certified": False}))
    assert client.post(f"/runs/{RUN}/mutation").status_code == 400
    run_json.write_text(json.dumps(meta))
    (tmp_path / RUN / "visitor").write_text("delivery-x\n")
    r = client.post(f"/runs/{RUN}/mutation")
    assert r.status_code == 400 and "visitor" in r.json()["detail"]


def test_one_job_at_a_time_and_a_pause_between_jobs(client, monkeypatch):
    fake_cli(monkeypatch, {**VALID, "runId": RUN})
    assert client.post(f"/runs/{RUN}/mutation").status_code == 200
    again = client.post(f"/runs/{RUN}/mutation")
    assert again.status_code == 429 and "try again" in again.json()["detail"]
    monkeypatch.setattr(mutation, "_last_finished", 0.0)
    assert mutation._lock.acquire(blocking=False)
    try:
        assert client.post(f"/runs/{RUN}/mutation").status_code == 429  # a re-verification or another mutation holds it
    finally:
        mutation._lock.release()


def test_a_failed_job_is_a_502_not_a_made_up_report(client, monkeypatch):
    fake_cli(monkeypatch, None)
    assert client.post(f"/runs/{RUN}/mutation").status_code == 502
    def boom(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 1)
    monkeypatch.setattr(mutation.subprocess, "run", boom)
    monkeypatch.setattr(mutation, "_last_finished", 0.0)
    assert client.post(f"/runs/{RUN}/mutation").status_code == 502
