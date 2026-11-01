import json
from types import SimpleNamespace

import jsonschema
import pytest

from diocle_api import deliver

CONTRACTS = deliver.REPO_ROOT / "contracts"


def test_target_must_be_an_allowed_github_repo(monkeypatch):
    monkeypatch.setenv("DIOCLE_IMPORT_OWNERS", "Nivetha200111")
    assert deliver.target_repo("https://github.com/Nivetha200111/quillmark-modern") == "Nivetha200111/quillmark-modern"
    for bad in ("https://github.com/someone/repo", "https://gitlab.com/Nivetha200111/x", "--upload-pack=x",
                "https://github.com/Nivetha200111"):
        with pytest.raises(SystemExit):
            deliver.target_repo(bad)


def test_certificate_uses_the_runs_real_seed_and_matches_the_contract(tmp_path, monkeypatch):
    monkeypatch.setattr(deliver, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(deliver, "_sh", lambda cmd, **kw: SimpleNamespace(stdout="cobc (GnuCOBOL) 3.2.0\n"))
    legacy = tmp_path / "runs" / "imports" / "o-legacy-abcdef123456"
    (legacy / "copybooks").mkdir(parents=True)
    (legacy / "copybooks" / "REC.cpy").write_text("")
    (tmp_path / "runs" / "r1" / "java").mkdir(parents=True)
    (tmp_path / "runs" / "r1" / "java" / "Prog.java").write_text("")
    report = {"source": {"location": "https://github.com/o/legacy", "commit": "abcdef1234567890" * 2 + "abcdefgh"}}
    program = {"name": "PROG", "path": "cobol/PROG.cbl", "copybooks": ["REC"], "job": None,
               "copybookPaths": {"REC": "QMK.PROD.COPYLIB/REC"}}
    run = {"id": "r1", "command": "repair", "rounds": [], "certificationSeed": 4242, "model": "m",
           "after": {"passed": 10, "total": 10, "stdoutMatch": True},
           "efficiency": {"modelCalls": 0, "totalTokens": 0, "estimatedCostUsd": 0.0}, "memory": None}
    cert = deliver.certificate(run, {"javaConversion": {"mainClass": "Prog"}}, report, program, "c0ffee")
    jsonschema.validate(cert, json.loads((CONTRACTS / "certificate.schema.json").read_text()))
    assert cert["verification"]["seed"] == 4242  # a no-repair run certified on CERT_SEED, not CERT_SEED + 0 rounds
    assert cert["legacy"]["copybooks"] == ["QMK.PROD.COPYLIB/REC"] and cert["java"]["files"] == ["Prog.java"]


def test_pr_body_credits_the_models_not_the_coding_assistant():
    run = {"before": {"passed": 1, "total": 2}}
    cert = {"program": "P", "verification": {"passed": 2, "total": 2, "stdoutMatch": True},
            "agent": {"modelCalls": 1, "rounds": 1, "memoryLessonsUsed": 0, "estimatedCostUsd": 0.001}}
    body = deliver._pr_body({"source": {"location": "https://github.com/o/r", "commit": "a" * 40}}, [(run, cert)], [])
    assert "Muse Spark" in body and "Claude" not in body


def test_pr_body_survives_an_unpriced_model():
    cert = {"program": "P", "verification": {"passed": 2, "total": 2, "stdoutMatch": True},
            "agent": {"modelCalls": 1, "rounds": 1, "memoryLessonsUsed": 0, "estimatedCostUsd": None}}
    body = deliver._pr_body({"source": {"location": "https://github.com/o/r", "commit": "a" * 40}}, [({}, cert)], [])
    assert "| n/a |" in body


def _scope_run(**over):
    return {"after": {"passed": 5, "total": 5, "stdoutMatch": True}, "breaker": None, "guard": None, "crosscheck": None, **over}


def test_a_check_that_did_not_happen_is_never_recorded_as_passed():
    scope = deliver.certificate_scope(_scope_run())
    assert scope["attack"] == {"status": "not-run"} and scope["guardReview"] == "not-run" and scope["crossCheck"] == "not-run"
    zero = deliver.certificate_scope(_scope_run(breaker={"tried": 0, "broke": 0}))
    assert zero["attack"] == {"status": "not-run"}
    capped = deliver.certificate_scope(_scope_run(guard={"review": {"verdict": "error", "summary": "review skipped: cap"}}))
    assert capped["guardReview"] == "skipped"
    done = deliver.certificate_scope(_scope_run(breaker={"tried": 24, "broke": 2}, guard={"review": {"verdict": "pass"}}))
    assert done["attack"] == {"status": "broken-and-repaired", "tried": 24, "broke": 2} and done["guardReview"] == "pass"
    assert any("IBM Enterprise COBOL" in x for x in scope["notEstablished"]) and any("Formal equivalence" in x for x in scope["notEstablished"])


def test_stand_ins_reach_the_certificate_and_the_pull_request():
    run = _scope_run(after={"passed": 5, "total": 5, "stdoutMatch": True, "database": {"engine": "SQLite"}, "keyed": {"engine": "bdb"},
                            "standIns": [{"routine": "CEE3ABD", "exitCode": 16, "note": "n"}]})
    scope = deliver.certificate_scope(run)
    assert [s.split()[0] for s in scope["standIns"]] == ["SQLite", "Berkeley", "Diocle's"]
    cert = {"program": "P", "scope": scope, "verification": {"passed": 5, "total": 5, "stdoutMatch": True},
            "agent": {"modelCalls": 1, "rounds": 0, "memoryLessonsUsed": 0, "estimatedCostUsd": 0.01}}
    body = deliver._pr_body({"source": {"location": "https://github.com/o/r", "commit": "a" * 40}}, [(run, cert)], [])
    assert "SQLite stands in for DB2" in body and "IBM Enterprise COBOL" in body and "Not a pass" in body
    assert "**not run**" in body and "| not run |" in body
