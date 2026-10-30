"""GET /runs/{id}/reproducers: read-only passthrough of the verifier's minimal-reproducer records."""

import base64
import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from diocle_api.app import app

CONTRACTS = Path(__file__).resolve().parents[3] / "contracts"
EXAMPLE = json.loads((CONTRACTS / "examples" / "minimal-reproducer.chqclr-nsf-fee.json").read_text())
RUN = "chq-20261030-101010"


@pytest.fixture
def client(tmp_path, monkeypatch):
    run = tmp_path / RUN
    (run / "reproducers").mkdir(parents=True)
    (run / "regression" / EXAMPLE["id"]).mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"program": "CHQCLR", "command": "run", "certified": True, "sample": "samples/none",
                                              "reproducers": [{"id": EXAMPLE["id"], "status": "minimized"}]}))
    (run / "reproducers" / f"{EXAMPLE['id']}.json").write_text(json.dumps(EXAMPLE))
    for name, data in (("case.json", b"{}"), ("input.dat", b"R\xff"), ("expected-output.dat", b"x"), ("expected-stdout.txt", b"")):
        (run / "regression" / EXAMPLE["id"] / name).write_bytes(data)
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    return TestClient(app)


def test_serves_the_saved_records_unchanged(client):
    body = client.get(f"/runs/{RUN}/reproducers").json()
    assert body["runId"] == RUN and body["reproducers"] == [EXAMPLE]
    jsonschema.validate(body["reproducers"][0], json.loads((CONTRACTS / "minimal-reproducer.schema.json").read_text()))


def test_run_detail_passes_the_summaries_through_and_stays_valid(client):
    run = client.get(f"/runs/{RUN}").json()
    jsonschema.validate(run, json.loads((CONTRACTS / "run.schema.json").read_text()))
    assert run["reproducers"] == [{"id": EXAMPLE["id"], "status": "minimized"}]


def test_a_run_without_reproducers_is_an_empty_list_and_unknown_runs_are_404(client, tmp_path):
    other = tmp_path / "plain-20261030-111111"
    other.mkdir()
    (other / "run.json").write_text(json.dumps({"program": "P", "command": "run", "certified": True}))
    assert client.get("/runs/plain-20261030-111111/reproducers").json()["reproducers"] == []
    assert client.get("/runs/missing/reproducers").status_code == 404
    assert client.get("/runs/..%2Fx/reproducers").status_code == 404


def test_files_that_are_not_records_of_this_case_are_ignored(client, tmp_path):
    folder = tmp_path / RUN / "reproducers"
    (folder / "other.json").write_text(json.dumps({**EXAMPLE, "id": "not-other"}))  # id differs from the file name
    (folder / "junk.json").write_text("{not json")
    (folder / "v2.json").write_text(json.dumps({**EXAMPLE, "id": "v2", "version": "9.9"}))
    assert [r["id"] for r in client.get(f"/runs/{RUN}/reproducers").json()["reproducers"]] == [EXAMPLE["id"]]


def test_visitor_runs_are_withheld(client, tmp_path):
    (tmp_path / RUN / "visitor").write_text("")
    assert client.get(f"/runs/{RUN}/reproducers").status_code == 404
    assert client.get(f"/runs/{RUN}/reproducers/{EXAMPLE['id']}/regression").status_code == 404


def test_regression_case_download_is_the_four_files(client):
    body = client.get(f"/runs/{RUN}/reproducers/{EXAMPLE['id']}/regression").json()
    assert [f["name"] for f in body["files"]] == ["case.json", "input.dat", "expected-output.dat", "expected-stdout.txt"]
    assert base64.b64decode(body["files"][1]["base64"]) == b"R\xff"
    assert client.get(f"/runs/{RUN}/reproducers/nope/regression").status_code == 404
    assert client.get(f"/runs/{RUN}/reproducers/..%2Fx/regression").status_code == 404


def test_the_endpoints_are_get_only(client):
    assert client.post(f"/runs/{RUN}/reproducers").status_code == 405
