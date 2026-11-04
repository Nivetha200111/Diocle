"""Every new delivery records the analyzer's links as soon as analysis finishes. Analyzer and converter are TEST DOUBLES."""

import json
from pathlib import Path

import jsonschema
import pytest

from diocle_api import deliver, deliveries

DELIVERY = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "delivery.schema.json").read_text())


def edge(a, b, kind="copy"):
    return {"from": a, "to": b, "kind": kind}


def test_only_the_tree_kinds_each_distinct_link_once_in_analyzer_order():
    tree = deliver.dependency_tree({"dependencies": [
        edge("B", "COPYB"), edge("A", "COPYA"), edge("B", "COPYB"), edge("A", "COPYA", "call"), edge("A", "DS.NAME", "file"),
        edge("A", "X", "other"), edge("JOB1", "A", "job")]})
    assert tree == {"edges": [edge("B", "COPYB"), edge("A", "COPYA"), edge("A", "COPYA", "call"), edge("JOB1", "A", "job")],
                    "total": 4, "truncated": False}


def test_the_cap_says_it_truncated():
    tree = deliver.dependency_tree({"dependencies": [edge("P", f"C{i}") for i in range(deliver.MAX_TREE_EDGES + 5)]})
    assert len(tree["edges"]) == deliver.MAX_TREE_EDGES
    assert tree["edges"][0] == edge("P", "C0")
    assert tree["total"] == deliver.MAX_TREE_EDGES + 5 and tree["truncated"] is True
    jsonschema.validate({"id": "d", "legacy": {"repository": "u"}, "target": None, "stage": "done", "programs": [], "startedAt": "t",
                         "dependencyTree": tree}, DELIVERY)


def test_exactly_at_the_cap_is_not_truncated():
    tree = deliver.dependency_tree({"dependencies": [edge("P", f"C{i}") for i in range(deliver.MAX_TREE_EDGES)]})
    assert tree["truncated"] is False and tree["total"] == deliver.MAX_TREE_EDGES


def test_hostile_or_malformed_labels_stay_small_and_plain():
    tree = deliver.dependency_tree({"dependencies": [
        edge("A" * 500, "B\x1b[31m‮"), edge("", "B"), edge("A", None), edge(1, "B"), "not an edge", edge("<b>x</b>", "y")]})
    assert [e["from"] for e in tree["edges"]] == ["A" * 120, "<b>x</b>"]  # kept as data: the page renders it as text
    assert tree["edges"][0]["to"] == "B?[31m?"
    jsonschema.validate(tree, DELIVERY["properties"]["dependencyTree"])


def test_a_report_without_the_field_records_nothing():
    assert deliver.dependency_tree({}) is None
    assert deliver.dependency_tree({"dependencies": "nope"}) is None
    assert deliver.dependency_tree({"dependencies": []}) == {"edges": [], "total": 0, "truncated": False}


def program(name):
    return {"name": name, "path": f"src/{name}.cbl", "convertible": True, "notConvertibleReason": None, "copybooks": [],
            "copybookPaths": {}, "files": []}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(deliver, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    monkeypatch.delenv("DIOCLE_CONVERT_ANYWAY", raising=False)
    samples = tmp_path / "samples" / "a"
    samples.mkdir(parents=True)
    (samples / "A.cbl").write_text("X\n")
    (samples / "sample.json").write_text(json.dumps({"source": "A.cbl"}))
    return tmp_path, monkeypatch


def stored(tmp_path):
    return json.loads(next((tmp_path / "runs" / "deliveries").glob("*/delivery.json")).read_text())


def analyzer_gives(tmp_path, monkeypatch, programs):
    report = {"source": {"location": "u", "commit": "a" * 40}, "programs": programs, "dependencies": [edge("A", "COPYA"), edge("A", "B", "call")]}
    monkeypatch.setattr(deliver, "analyze", lambda *a, **k: (report, tmp_path / "samples"))


def test_recorded_before_the_precheck_and_before_conversion_for_a_visitor_import(env):
    tmp_path, monkeypatch = env
    analyzer_gives(tmp_path, monkeypatch, [program("A")])
    seen = {}

    class Precheck:
        def __init__(self, *a, **k):
            seen["precheck"] = stored(tmp_path)

        def failure(self, name):
            return None

        def record(self):
            return {}

    def fake_convert(*a, **k):
        seen["convert"] = stored(tmp_path)
        return None

    monkeypatch.setattr(deliver, "CompilePrecheck", Precheck)
    monkeypatch.setattr(deliver, "convert", fake_convert)
    assert deliver.main(["https://github.com/o/r", "--public"]) == 0
    for moment in ("precheck", "convert"):
        assert seen[moment]["dependencyTree"]["total"] == 2
        assert seen[moment]["legacy"]["commit"] == "a" * 40
    final = stored(tmp_path)
    jsonschema.validate(final, DELIVERY)
    assert final["public"] is True and final["dependencyTree"]["edges"][1] == edge("A", "B", "call")


def test_a_repository_with_nothing_to_convert_still_has_its_tree(env):
    tmp_path, monkeypatch = env
    analyzer_gives(tmp_path, monkeypatch, [{**program("A"), "convertible": False, "notConvertibleReason": "EXEC CICS"}])
    monkeypatch.setattr(deliver, "CompilePrecheck", lambda *a, **k: type("P", (), {"failure": lambda s, n: None, "record": lambda s: {}})())
    with pytest.raises(SystemExit):
        deliver.main(["https://github.com/o/r", "--public"])
    final = stored(tmp_path)
    jsonschema.validate(final, DELIVERY)
    assert final["stage"] == "failed" and final["dependencyTree"]["total"] == 2


def test_an_older_delivery_is_served_without_the_field(tmp_path, monkeypatch):
    monkeypatch.setenv("DIOCLE_RUNS_DIR", str(tmp_path))
    d = tmp_path / "deliveries" / "delivery-1"
    d.mkdir(parents=True)
    old = {"id": "delivery-1", "legacy": {"repository": "u", "commit": None}, "target": None, "stage": "done", "startedAt": "t",
           "finishedAt": None, "error": None, "programs": [], "pullRequest": None}
    (d / "delivery.json").write_text(json.dumps(old))
    served = deliveries.get_delivery("delivery-1")
    jsonschema.validate(served, DELIVERY)
    assert "dependencyTree" not in served
