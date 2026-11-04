"""The API's side of the capped drawing: who gets one, how it starts, and what is served. The drawing job itself is a TEST DOUBLE
here; its caps and failure paths are tested in services/converter/tests/test_treedraw.py."""

import json
import subprocess
import time
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient

from diocle_api import app as app_module
from diocle_api import deliver, deliveries, public

DELIVERY = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "delivery.schema.json").read_text())
PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 40
PASSED = {"status": "passed", "reason": None, "verified": True, "model": "m", "readModel": "r", "passedOnAttempt": 2, "mediaType": "image/png",
          "part": {"program": "P", "edges": [["P", "A"], ["P", "B"]]}, "attempts": [{"attempt": 1, "outcome": "no-match"}, {"attempt": 2, "outcome": "match"}],
          "imagesDrawn": 2, "tokenUsage": {"image": {"total_tokens": 9}, "read": {}}, "readCostUsd": 0.02, "startedAt": "t", "finishedAt": "t"}


@pytest.fixture
def runs(tmp_path, monkeypatch):
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    d = tmp_path / "deliveries" / "delivery-1"
    d.mkdir(parents=True)
    (d / "delivery.json").write_text(json.dumps({"id": "delivery-1", "legacy": {"repository": "u", "commit": None}, "target": None, "stage": "done",
                                                 "startedAt": "t", "finishedAt": None, "error": None, "programs": [], "pullRequest": None}))
    return d


@pytest.fixture
def client():
    return TestClient(app_module.app)


def put(d, record, image=PNG, name="tree-drawing.png"):
    (d / "tree-drawing.json").write_text(json.dumps(record))
    if image is not None:
        (d / name).write_bytes(image)


def test_a_passed_drawing_is_served_with_its_type_and_merged_into_the_record(runs, client):
    put(runs, PASSED)
    r = client.get("/deliveries/delivery-1/dependency-drawing")
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["content-type"] == "image/png" and r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == "default-src 'none'"
    served = client.get("/deliveries/delivery-1").json()
    jsonschema.validate(served, DELIVERY)
    assert served["dependencyDrawing"]["passedOnAttempt"] == 2


@pytest.mark.parametrize("record", [
    {**PASSED, "status": "failed", "verified": False}, {**PASSED, "status": "drawing"}, {**PASSED, "verified": False},
    {**PASSED, "status": "not-drawn"}, {**PASSED, "mediaType": "text/html"}, {**PASSED, "mediaType": "../../secret"}, {**PASSED, "mediaType": ["image/png"]}])
def test_only_a_drawing_that_passed_is_ever_served(runs, client, record):
    put(runs, record)
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404


def test_no_record_and_a_garbage_record_serve_nothing_and_do_not_break_the_delivery(runs, client):
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404
    (runs / "tree-drawing.json").write_text("not json")
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404
    assert "dependencyDrawing" not in client.get("/deliveries/delivery-1").json()


def test_a_missing_or_wrong_file_is_not_served(runs, client):
    put(runs, PASSED, image=None)
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404
    put(runs, PASSED, image=b"<script>alert(1)</script>")
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404


def test_a_file_over_the_size_cap_is_not_served(runs, client, monkeypatch):
    monkeypatch.setattr(deliveries, "MAX_DRAWING_BYTES", 10)
    put(runs, PASSED)
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404


def test_a_symlink_is_not_followed(runs, client, tmp_path):
    secret = tmp_path / "secret.png"
    secret.write_bytes(PNG)
    put(runs, PASSED, image=None)
    (runs / "tree-drawing.png").symlink_to(secret)
    assert client.get("/deliveries/delivery-1/dependency-drawing").status_code == 404


@pytest.mark.parametrize("bad", ["..", ".hidden", "delivery-1%2f..", "..%2f..%2fetc", "no-such-delivery"])
def test_no_path_can_come_from_the_request(runs, client, bad):
    put(runs, PASSED)
    assert client.get(f"/deliveries/{bad}/dependency-drawing").status_code == 404


def test_a_job_that_died_stops_saying_drawing(runs, monkeypatch):
    put(runs, {**PASSED, "status": "drawing", "verified": False, "mediaType": None, "passedOnAttempt": None, "attempts": [{"attempt": 1, "outcome": "image-error"}]}, image=None)
    assert deliveries.get_delivery("delivery-1")["dependencyDrawing"]["status"] == "drawing"
    monkeypatch.setattr(deliveries, "DRAWING_STALE_SECONDS", -1)
    served = deliveries.get_delivery("delivery-1")["dependencyDrawing"]
    assert served["status"] == "not-drawn" and served["reason"] == "job-stopped"
    jsonschema.validate(served, DELIVERY["properties"]["dependencyDrawing"])


# Who gets a drawing


@pytest.fixture
def fresh_visitors(monkeypatch):
    monkeypatch.setattr(public, "_seen", {})


def test_off_means_no_flag_and_no_visitor_counted(monkeypatch, fresh_visitors):
    monkeypatch.delenv("TREE_IMAGE_MODEL_ID", raising=False)
    assert public.tree_drawing_mode("1.2.3.4") is None and public.tree_drawing_mode(None) is None
    monkeypatch.setenv("TREE_IMAGE_MODEL_ID", "")
    assert public.tree_drawing_mode("1.2.3.4") is None
    assert not public._seen


def test_one_drawing_job_per_visitor_a_day_and_the_visitors_are_separate(monkeypatch, fresh_visitors):
    monkeypatch.setenv("TREE_IMAGE_MODEL_ID", "m")
    assert public.tree_drawing_mode("1.2.3.4") == "draw"
    assert public.tree_drawing_mode("1.2.3.4") == "visitor-cap"
    assert public.tree_drawing_mode("5.6.7.8") == "draw"
    key = f"tree-drawing:{public.visitor_key('1.2.3.4')}"
    public._seen[key] = [time.time() - 90000]
    assert public.tree_drawing_mode("1.2.3.4") == "draw"


def test_the_drawing_bucket_does_not_touch_the_import_limit(monkeypatch, fresh_visitors):
    monkeypatch.setenv("TREE_IMAGE_MODEL_ID", "m")
    monkeypatch.setenv("DIOCLE_PUBLIC_PER_VISITOR", "1")
    monkeypatch.setattr(public, "spent_today", lambda: 0.0)
    public.tree_drawing_mode("1.2.3.4")
    public.admit("1.2.3.4")  # the one import this visitor has left


def test_its_spend_is_not_in_the_import_budget(runs, monkeypatch):
    put(runs, {**PASSED, "readCostUsd": 99.0})
    from diocle_api import asks, livesamples
    monkeypatch.setattr(asks, "spent", lambda: 0.0)
    monkeypatch.setattr(livesamples, "printout_spent", lambda: 0.0)
    assert public.spent_today() == 0.0


def visitor_post(client, monkeypatch, mode_env="m", budget_spent=0.0):
    monkeypatch.setenv("DIOCLE_HOSTED", "1")
    monkeypatch.setenv("DIOCLE_ADMIN_TOKEN", "secret")
    monkeypatch.setenv("DIOCLE_PUBLIC_IMPORTS", "1")
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    monkeypatch.setenv("TREE_IMAGE_MODEL_ID", mode_env)
    monkeypatch.setattr(public, "spent_today", lambda: budget_spent)
    started = []
    monkeypatch.setattr(app_module, "start_delivery", lambda *a, **k: started.append(k) or "delivery-x")
    monkeypatch.setattr(app_module, "running_delivery", lambda: None)
    monkeypatch.setattr(app_module.livesamples, "running_job", lambda: None)
    r = client.post("/deliveries", json={"legacy": "https://github.com/o/r"})
    return r, started


def test_a_visitor_import_asks_for_a_drawing_then_goes_ahead_without_one(client, monkeypatch, fresh_visitors):
    r, started = visitor_post(client, monkeypatch)
    assert r.status_code == 202 and started[0]["tree_drawing"] == "draw" and started[0]["public"] is True
    r = client.post("/deliveries", json={"legacy": "https://github.com/o/r"})
    assert r.status_code == 202 and started[1]["tree_drawing"] == "visitor-cap"


def test_a_visitor_with_the_feature_off_gets_no_flag(client, monkeypatch, fresh_visitors):
    r, started = visitor_post(client, monkeypatch, mode_env="")
    assert r.status_code == 202 and started[0]["tree_drawing"] is None


def test_a_used_up_import_budget_refuses_the_import_as_before_and_counts_no_drawing(client, monkeypatch, fresh_visitors):
    r, started = visitor_post(client, monkeypatch, budget_spent=100.0)
    assert r.status_code == 429 and not started and not public._seen


def test_the_flag_reaches_the_delivery_command_line(tmp_path, monkeypatch):
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    seen = {}

    class FakePopen:
        def __init__(self, cmd, **kw):
            seen["cmd"] = cmd

        def poll(self):
            return None

    monkeypatch.setattr(deliveries.subprocess, "Popen", FakePopen)
    deliveries.start_delivery("https://github.com/o/r", None, False, False, public=True, tree_drawing="draw")
    assert seen["cmd"][seen["cmd"].index("--tree-drawing") + 1] == "draw"
    deliveries._procs.clear()
    (tmp_path / "deliveries").rename(tmp_path / "older")
    deliveries.start_delivery("https://github.com/o/r", None, False, False, public=True)
    assert "--tree-drawing" not in seen["cmd"]
    deliveries._procs.clear()


# The delivery carries on, whatever happens to the drawing


def program(name):
    return {"name": name, "path": f"src/{name}.cbl", "convertible": True, "notConvertibleReason": None, "copybooks": [], "copybookPaths": {}, "files": []}


@pytest.fixture
def delivery_env(tmp_path, monkeypatch):
    monkeypatch.setattr(deliver, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    monkeypatch.setenv("TREE_IMAGE_MODEL_ID", "m")
    monkeypatch.setenv("META_MODEL_API_KEY", "fake")
    monkeypatch.setenv("GH_TOKEN", "must-not-reach-the-job")
    samples = tmp_path / "samples" / "a"
    samples.mkdir(parents=True)
    (samples / "A.cbl").write_text("X\n")
    (samples / "sample.json").write_text(json.dumps({"source": "A.cbl"}))
    report = {"source": {"location": "u", "commit": "a" * 40}, "programs": [program("A")],
              "dependencies": [{"from": "A", "to": "B", "kind": "copy"}, {"from": "A", "to": "C", "kind": "copy"}]}
    monkeypatch.setattr(deliver, "analyze", lambda *a, **k: (report, tmp_path / "samples"))
    monkeypatch.setattr(deliver, "CompilePrecheck", lambda *a, **k: type("P", (), {"failure": lambda s, n: None, "record": lambda s: {}})())
    return tmp_path, monkeypatch


def stored(tmp_path):
    return json.loads(next((tmp_path / "runs" / "deliveries").glob("*/delivery.json")).read_text())


def join_drawing():
    import threading
    for t in threading.enumerate():
        if t.name == "tree-drawing":
            t.join(10)


def test_the_job_starts_after_the_tree_is_recorded_and_does_not_hold_up_conversion(delivery_env):
    tmp_path, monkeypatch = delivery_env
    import threading
    release, seen = threading.Event(), {}

    def fake_job(cmd, **kw):
        seen.update(cmd=cmd, env=kw["env"], tree=stored(tmp_path).get("dependencyTree"))
        assert release.wait(10)

    def fake_convert(*a, **k):
        seen["converted_while_drawing"] = not release.is_set()
        release.set()

    monkeypatch.setattr(deliver.subprocess, "run", fake_job)
    monkeypatch.setattr(deliver, "convert", fake_convert)
    assert deliver.main(["https://github.com/o/r", "--public", "--tree-drawing", "draw"]) == 0
    join_drawing()
    assert seen["converted_while_drawing"] is True and seen["tree"]["total"] == 2
    assert seen["cmd"][-4:-2] == ["tree-draw", str(next((tmp_path / "runs" / "deliveries").iterdir()))]
    assert seen["cmd"][-1] == str(tmp_path / "runs" / "tree-drawings" / "images.jsonl")
    assert "GH_TOKEN" not in seen["env"] and seen["env"]["TREE_IMAGE_MODEL_ID"] == "m"


@pytest.mark.parametrize("failure", [OSError("no such file"), subprocess.TimeoutExpired("job", 1), ValueError("anything")])
def test_a_job_that_cannot_run_never_fails_the_delivery(delivery_env, failure):
    tmp_path, monkeypatch = delivery_env

    def boom(*a, **k):
        raise failure

    monkeypatch.setattr(deliver.subprocess, "run", boom)
    monkeypatch.setattr(deliver, "convert", lambda *a, **k: None)
    assert deliver.main(["https://github.com/o/r", "--public", "--tree-drawing", "draw"]) == 0
    join_drawing()
    final = stored(tmp_path)
    assert final["stage"] == "done" and final["dependencyTree"]["total"] == 2


def test_a_thread_that_cannot_start_never_fails_the_delivery(delivery_env):
    tmp_path, monkeypatch = delivery_env

    class NoThread:
        def __init__(self, *a, **k):
            raise RuntimeError("can't start new thread")

    monkeypatch.setattr(deliver.threading, "Thread", NoThread)
    monkeypatch.setattr(deliver, "convert", lambda *a, **k: None)
    assert deliver.main(["https://github.com/o/r", "--public", "--tree-drawing", "draw"]) == 0
    assert stored(tmp_path)["stage"] == "done"


def test_an_empty_model_id_starts_nothing_and_writes_nothing(delivery_env):
    tmp_path, monkeypatch = delivery_env
    monkeypatch.setenv("TREE_IMAGE_MODEL_ID", "")

    def must_not_run(*a, **k):
        raise AssertionError("the job must not start")

    monkeypatch.setattr(deliver.subprocess, "run", must_not_run)
    monkeypatch.setattr(deliver, "convert", lambda *a, **k: None)
    assert deliver.main(["https://github.com/o/r", "--public", "--tree-drawing", "draw"]) == 0
    d = next((tmp_path / "runs" / "deliveries").iterdir())
    assert not (d / "tree-drawing.json").exists() and not (d / "tree-drawing.log").exists()


def test_no_flag_starts_nothing(delivery_env):
    tmp_path, monkeypatch = delivery_env

    def must_not_run(*a, **k):
        raise AssertionError("the job must not start")

    monkeypatch.setattr(deliver.subprocess, "run", must_not_run)
    monkeypatch.setattr(deliver, "convert", lambda *a, **k: None)
    assert deliver.main(["https://github.com/o/r", "--public"]) == 0


def test_a_visitor_past_their_drawing_gets_a_note_and_no_job(delivery_env):
    tmp_path, monkeypatch = delivery_env

    def must_not_run(*a, **k):
        raise AssertionError("the job must not start")

    monkeypatch.setattr(deliver.subprocess, "run", must_not_run)
    monkeypatch.setattr(deliver, "convert", lambda *a, **k: None)
    assert deliver.main(["https://github.com/o/r", "--public", "--tree-drawing", "visitor-cap"]) == 0
    d = next((tmp_path / "runs" / "deliveries").iterdir())
    record = json.loads((d / "tree-drawing.json").read_text())
    jsonschema.validate(record, DELIVERY["properties"]["dependencyDrawing"])
    assert record["reason"] == "visitor-cap"


def test_the_drawing_job_writes_only_its_own_files_so_delivery_json_stays_with_the_delivery():
    # delivery.json is rewritten by the delivery alone: the job gets the directory and has no way to the Progress object.
    src = (Path(deliver.__file__)).read_text()
    assert "progress" not in src[src.index("def _run_tree_drawing"):src.index("def start_tree_drawing")]
