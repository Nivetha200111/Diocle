"""Editor commands and contracts/editor-result.schema.json. The pipeline/analyzer seams are labelled STUBS (no model call, no network)."""

import json
import shutil
from pathlib import Path

import jsonschema
import pytest

from diocle_converter import editor

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = json.loads((ROOT / "contracts" / "editor-result.schema.json").read_text())
REPO = ROOT / "samples" / "convert-anyway-repo"
needs_cobc = pytest.mark.skipif(shutil.which("cobc") is None, reason="GnuCOBOL not installed")

VALID = [
    {"version": "0.1", "command": "check", "ok": True, "diagnostics": []},
    {"version": "0.1", "command": "check", "ok": False, "file": "a.cbl",
     "diagnostics": [{"file": "a.cbl", "line": 5, "severity": "error", "message": "syntax error"}]},
    {"version": "0.1", "command": "convert", "ok": True, "assurance": "certified", "maxUsd": 0.25, "costUsd": 0.003, "model": "m",
     "runDir": "/x", "files": {"java": ["/x/java/A.java"]}},
    {"version": "0.1", "command": "convert", "ok": True, "assurance": "certified-against-repaired-cobol", "maxUsd": 0.25,
     "costUsd": None, "model": None, "files": {"diff": "/x/d", "repairedCobol": "/x/a.repaired.cbl"}, "repairedLines": 1},
    {"version": "0.1", "command": "convert", "ok": False, "error": "no key"},
]
INVALID = [
    {"version": "0.1", "command": "check", "ok": True},  # check needs diagnostics
    {"version": "0.2", "command": "check", "ok": True, "diagnostics": []},
    {"version": "0.1", "command": "convert", "ok": True, "assurance": "certified"},  # maxUsd missing
    {"version": "0.1", "command": "convert", "ok": True, "assurance": "proven", "maxUsd": 1},
    {"version": "0.1", "command": "check", "ok": True, "diagnostics": [{"file": "a", "line": 0, "severity": "error", "message": "x"}]},
    {"version": "0.1", "command": "check", "ok": True, "diagnostics": [], "apiKey": "x"},
    {"version": "0.1", "command": "convert", "ok": True, "assurance": "skipped", "maxUsd": 1, "files": {"zip": "x"}},
]


@pytest.mark.parametrize("doc", VALID)
def test_valid_examples(doc):
    jsonschema.validate(doc, CONTRACT)


@pytest.mark.parametrize("doc", INVALID)
def test_invalid_examples(doc):
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, CONTRACT)


def test_parse_diagnostics_keeps_only_compiler_lines():
    text = "/w/a.cbl:12: error: 'X' is not defined\n   12 |  MOVE X\n/w/c.cpy:3: warning: odd\nnoise\n"
    assert editor.parse_diagnostics(text) == [
        {"file": "/w/a.cbl", "line": 12, "severity": "error", "message": "'X' is not defined"},
        {"file": "/w/c.cpy", "line": 3, "severity": "warning", "message": "odd"}]


@needs_cobc
def test_check_good_and_bad_files_validate_against_the_contract():
    cb = [str(REPO / "copybooks")]
    good = editor.check(str(REPO / "cobol" / "ADDFEE.cbl"), cb)
    bad = editor.check(str(REPO / "cobol" / "NOPERIOD.cbl"), cb)
    missing = editor.check(str(REPO / "cobol" / "NOPE.cbl"), cb)
    for r in (good, bad, missing):
        jsonschema.validate(r, CONTRACT)
    assert good["ok"] and good["diagnostics"] == []
    assert not bad["ok"] and bad["diagnostics"][0]["line"] == 5 and bad["diagnostics"][0]["severity"] == "error"
    assert not missing["ok"] and "not found" in missing["error"]


def fake_run(tmp_path, **fields):
    run = {"program": "ADDFEE", "certified": True, "status": "certified", "model": "stub-model",
           "usage": {"calls": 1, "inputTokens": 1, "outputTokens": 1, "estimatedCostUsd": 0.002}, **fields}
    d = tmp_path / "copy"
    (d / "java").mkdir(parents=True, exist_ok=True)
    (d / "java" / "Addfee.java").write_text("class Addfee {}")
    return run, d


def test_build_result_copies_the_record_and_validates(tmp_path):
    run, d = fake_run(tmp_path)
    r = editor.build_result("a.cbl", run, d, tmp_path, 0.25)
    jsonschema.validate(r, CONTRACT)
    assert r["assurance"] == "certified" and r["costUsd"] == 0.002 and r["model"] == "stub-model" and r["files"]["java"]


def test_only_a_record_that_says_certified_is_certified(tmp_path):
    run, d = fake_run(tmp_path, certified=False, assurance="certified", status="not-certified")
    assert editor.build_result("a.cbl", run, d, tmp_path, 0.25)["assurance"] == "failed"
    run, d = fake_run(tmp_path, certified=False, assurance="compiled-unverified", assuranceReason="EXEC SQL")
    r = editor.build_result("a.cbl", run, d, tmp_path, 0.25)
    assert r["assurance"] == "compiled-unverified" and r["assuranceReason"] == "EXEC SQL"
    run, d = fake_run(tmp_path, certified=False, assurance="made-up")
    assert editor.build_result("a.cbl", run, d, tmp_path, 0.25)["assurance"] == "failed"


def test_repaired_result_points_at_diff_and_patched_cobol(tmp_path):
    run, d = fake_run(tmp_path, certified=False, assurance="certified-against-repaired-cobol",
                      cobolRepair={"method": "deterministic", "diff": "-a\n+b\n", "diagnostics": [], "changedLines": 1, "outcome": "compiles"})
    sample = tmp_path / "s"
    (sample / "src").mkdir(parents=True)
    (sample / "src" / "N.repaired.cbl").write_text("x")
    editor._extras(run, sample, d)
    r = editor.build_result("a.cbl", run, d, sample, 0.25)
    jsonschema.validate(r, CONTRACT)
    assert r["repairedLines"] == 1 and r["files"]["diff"].endswith("cobol-repair.diff") and r["files"]["repairedCobol"].endswith(".repaired.cbl")


def test_caps_and_missing_key_are_refused_before_any_work(tmp_path, monkeypatch):
    src = tmp_path / "a.cbl"
    src.write_text("x")
    monkeypatch.chdir(tmp_path)
    assert "at most" in editor.convert(str(src), [], 5.0, False, tmp_path)["error"]
    assert "at most" in editor.convert(str(src), [], 0, False, tmp_path)["error"]
    for k in ("MODEL_MODE", "META_API_KEY", "MODEL_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(editor.Settings, "from_env", classmethod(lambda cls: (_ for _ in ()).throw(SystemExit("Missing in .env"))))
    r = editor.convert(str(src), [], 0.1, False, tmp_path)
    jsonschema.validate(r, CONTRACT)
    assert not r["ok"] and "Missing" in r["error"]


@needs_cobc
def test_convert_with_stubbed_pipeline_stages_copybooks_and_copies_the_run(tmp_path, monkeypatch, capsys):
    """STUB: run_pipeline is replaced by a function that writes a labelled fake run.json; nothing is converted by a model."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(editor.Settings, "from_env", classmethod(lambda cls: None))
    fake_root = tmp_path / "root"
    monkeypatch.setattr(editor, "REPO_ROOT", fake_root)
    seen = {}

    def stub_pipeline(sample, max_usd, anyway):
        seen.update(sample=sample, max_usd=max_usd, anyway=anyway, has_copybooks=any((sample.parent.parent.parent / "repo" / "copybooks").iterdir()))
        d = fake_root / "runs" / "addfee-stub"
        (d / "java").mkdir(parents=True)
        (d / "java" / "Addfee.java").write_text("class Addfee {}")
        (d / "run.json").write_text(json.dumps({"program": "ADDFEE", "certified": True, "model": "STUB", "usage": {"estimatedCostUsd": 0.0}}))
        return "addfee-stub", 0

    monkeypatch.setattr(editor, "run_pipeline", stub_pipeline)
    monkeypatch.setattr(editor, "run_analyzer", lambda repo, out, anyway: _fake_analyze(repo, out))
    monkeypatch.setattr(editor, "_extras", lambda *a: None)
    code = editor.main(["convert", str(REPO / "cobol" / "ADDFEE.cbl"), "--copybooks", str(REPO / "copybooks"), "--max-usd", "0.05"])
    out = json.loads(capsys.readouterr().out)
    jsonschema.validate(out, CONTRACT)
    assert code == 0 and out["assurance"] == "certified" and seen["max_usd"] == 0.05 and seen["has_copybooks"]
    assert Path(out["runDir"]).is_relative_to(tmp_path / ".diocle" / "runs") and Path(out["files"]["java"][0]).is_file()


def _fake_analyze(repo, out):
    s = out / "samples" / "addfee"
    (s / "copybooks").mkdir(parents=True)
    (s / "sample.json").write_text("{}")
    return {"programs": [{"name": "ADDFEE", "convertible": True}]}


def test_not_convertible_without_anyway_is_skipped_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(editor.Settings, "from_env", classmethod(lambda cls: None))
    monkeypatch.setattr(editor, "run_analyzer", lambda r, o, a: {"programs": [{"name": "SQLRPT", "convertible": False,
                                                                              "notConvertibleReason": "EXEC SQL not supported"}]})
    called = []
    monkeypatch.setattr(editor, "run_pipeline", lambda *a: called.append(1))
    r = editor.convert(str(REPO / "cobol" / "SQLRPT.cbl"), [], 0.1, False, tmp_path)
    jsonschema.validate(r, CONTRACT)
    assert r["assurance"] == "skipped" and "EXEC SQL" in r["assuranceReason"] and not called


def test_model_falls_back_to_the_usage_records(tmp_path):
    run, d = fake_run(tmp_path, model=None)
    run["usage"]["modelCalls"] = [{"role": "translator", "model": "stub-from-usage"}]
    assert editor.build_result("a.cbl", run, d, tmp_path, 0.25)["model"] == "stub-from-usage"


def test_staging_copies_only_copied_members_never_dotfiles(tmp_path):
    """A search folder such as the workspace root must not pull .env, keys or Makefiles into the staging copy."""
    src = tmp_path / "prog.cbl"
    src.write_text("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. P.\n       DATA DIVISION.\n       WORKING-STORAGE SECTION.\n       COPY REC1.\n")
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "REC1").write_text("       01  A  PIC X.\n       COPY REC2.\n")   # extensionless member, copies another
    (lib / "REC2.cpy").write_text("       01  B  PIC X.\n")
    (lib / "UNUSED.cpy").write_text("       01  C  PIC X.\n")
    (lib / ".env").write_text("SECRET=1\n")
    (lib / "id_rsa").write_text("-----BEGIN-----\n")
    dest = tmp_path / "stage"
    n = editor.stage_repo(src, [str(lib)], dest)
    names = sorted(p.name for p in (dest / "copybooks").iterdir())
    assert names == ["REC1", "REC2.cpy"] and n == 2
