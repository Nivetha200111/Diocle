"""A delivery with nothing to convert says why, program by program, before any model call. Analyzer and converter are TEST DOUBLES."""

import json
from pathlib import Path

import jsonschema
import pytest

from diocle_api import deliver

DELIVERY = json.loads((Path(__file__).resolve().parents[3] / "contracts" / "delivery.schema.json").read_text())
CICS = "EXEC CICS needs a transaction adapter, not supported (CICS and IMS are out of scope)"


def program(name, reason, path=None):
    return {"name": name, "path": path or f"src/{name}.cbl", "convertible": reason is None, "notConvertibleReason": reason,
            "copybooks": [], "copybookPaths": {}, "files": []}


def sample(tmp_path, name, lines):
    d = tmp_path / "samples" / name.lower()
    d.mkdir(parents=True)
    (d / f"{name}.cbl").write_text("\n".join(["X"] * lines) + "\n")
    (d / "sample.json").write_text(json.dumps({"source": f"{name}.cbl"}))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(deliver, "REPO_ROOT", tmp_path)
    for k in ("DIOCLE_CONVERT_ANYWAY", "DIOCLE_PUBLIC_MAX_PROGRAMS", "DIOCLE_PUBLIC_MAX_LINES"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DIOCLE_SANDBOX_URL", "http://sandbox")
    monkeypatch.setattr(deliver, "CompilePrecheck", lambda *a, **k: type("P", (), {"failure": lambda s, n: None, "record": lambda s: {}})())

    def no_model(*a, **k):
        raise AssertionError("no program may reach the converter")

    monkeypatch.setattr(deliver, "convert", no_model)
    return tmp_path, monkeypatch


def analyze_gives(tmp_path, monkeypatch, programs):
    monkeypatch.setattr(deliver, "analyze", lambda *a, **k: ({"source": {"location": "u", "commit": "a" * 40}, "programs": programs}, tmp_path / "samples"))


def record(tmp_path):
    d = json.loads(next((tmp_path / "runs" / "deliveries").glob("*/delivery.json")).read_text())
    jsonschema.validate(d, DELIVERY)
    return d


def stop(tmp_path, monkeypatch, programs, *flags):
    analyze_gives(tmp_path, monkeypatch, programs)
    with pytest.raises(SystemExit) as e:
        deliver.main(["https://github.com/o/r", *flags])
    return str(e.value), record(tmp_path)


def test_every_refused_program_is_listed_with_the_analyzers_reason(env):
    tmp_path, monkeypatch = env
    error, d = stop(tmp_path, monkeypatch, [program("AAA", CICS), program("BBB", CICS), program("CCC", "copybook(s) not found: X")], "--public")
    assert d["stage"] == "failed" and d["error"] == error and d["legacy"]["commit"] == "a" * 40
    assert error.startswith("no convertible programs (3 COBOL programs refused). 2 of them: EXEC CICS")
    assert "1 of them: copybook(s) not found: X" in error
    by = {p["name"]: p for p in d["programs"]}
    assert by["AAA"] == {"name": "AAA", "path": "src/AAA.cbl", "status": "skipped", "runId": None, "reason": CICS}
    assert by["CCC"]["reason"] == "copybook(s) not found: X"


def test_a_repository_with_no_cobol_says_so(env):
    tmp_path, monkeypatch = env
    error, d = stop(tmp_path, monkeypatch, [])
    assert error == "no convertible programs (no COBOL programs found)" and d["programs"] == []


def test_the_record_stays_small_and_the_error_still_counts_every_program(env):
    tmp_path, monkeypatch = env
    many = [program(f"P{i}", f"reason {i % 5}") for i in range(deliver.REFUSALS_LISTED + 20)]
    error, d = stop(tmp_path, monkeypatch, many)
    assert len(d["programs"]) == deliver.REFUSALS_LISTED
    assert f"({len(many)} COBOL programs refused)" in error and error.endswith("others for other reasons")


def test_a_long_reason_is_cut_in_the_record(env):
    tmp_path, monkeypatch = env
    _, d = stop(tmp_path, monkeypatch, [program("AAA", "x" * 1000)])
    assert len(d["programs"][0]["reason"]) == 300 and len(d["error"]) <= 500


def test_two_files_with_one_program_id_stay_two_entries_with_their_own_paths(env):
    tmp_path, monkeypatch = env
    _, d = stop(tmp_path, monkeypatch, [program("AAA", CICS), program("AAA", CICS, "other/AAA.cbl"), program("AAA", CICS, "old/AAA.cbl")])
    assert [p["path"] for p in d["programs"]] == ["src/AAA.cbl", "other/AAA.cbl", "old/AAA.cbl"]  # the page keys its cards on the path


def test_only_the_named_programs_are_reported(env):
    tmp_path, monkeypatch = env
    _, d = stop(tmp_path, monkeypatch, [program("AAA", CICS), program("BBB", "other")], "--programs", "AAA")
    assert [p["name"] for p in d["programs"]] == ["AAA"]


def test_a_name_that_matches_nothing_does_not_claim_the_repository_has_no_cobol(env):
    tmp_path, monkeypatch = env
    error, d = stop(tmp_path, monkeypatch, [program("AAA", CICS)], "--programs", "TYPO")
    assert error == "no convertible programs (none of the named programs was found)" and d["programs"] == []


def test_a_program_over_the_visitor_limit_is_listed_beside_the_refused_ones(env):
    tmp_path, monkeypatch = env
    sample(tmp_path, "LONG", 2000)
    error, d = stop(tmp_path, monkeypatch, [program("LONG", None), program("AAA", CICS)], "--public")
    assert error.startswith("no convertible programs within the visitor limits (2000 lines; visitor imports take up to 1500) "
                            "(1 COBOL program refused). 1 of them: EXEC CICS")
    assert [p["name"] for p in d["programs"]] == ["LONG", "AAA"] and all(p["status"] == "skipped" for p in d["programs"])


def test_a_long_compiler_message_does_not_push_the_counts_out_of_the_record(env):
    tmp_path, monkeypatch = env
    sample(tmp_path, "BAD", 10)
    monkeypatch.setattr(deliver, "CompilePrecheck", lambda *a, **k: type("P", (), {"failure": lambda s, n: "y" * 900, "record": lambda s: {}})())
    _, d = stop(tmp_path, monkeypatch, [program("BAD", None), program("AAA", CICS)], "--public")
    assert "(1 COBOL program refused). 1 of them: EXEC CICS" in d["error"] and len(d["error"]) <= 500


def test_a_repository_with_something_to_convert_is_not_touched(env):
    tmp_path, monkeypatch = env
    converted = []
    monkeypatch.setattr(deliver, "convert", lambda sample_dir, *a, **k: converted.append(sample_dir.name))
    analyze_gives(tmp_path, monkeypatch, [program("AAA", None), program("BBB", CICS)])
    assert deliver.main(["https://github.com/o/r"]) == 0
    d = record(tmp_path)
    assert converted == ["aaa"] and d["stage"] == "done" and d["error"] is None
    assert [p["name"] for p in d["programs"]] == ["AAA"]  # refused programs are listed only when nothing can be converted
