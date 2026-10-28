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
    program = {"name": "PROG", "path": "cobol/PROG.cbl", "copybooks": ["REC"], "job": None}
    run = {"id": "r1", "command": "repair", "rounds": [], "certificationSeed": 4242, "model": "m",
           "after": {"passed": 10, "total": 10, "stdoutMatch": True},
           "efficiency": {"modelCalls": 0, "totalTokens": 0, "estimatedCostUsd": 0.0}, "memory": None}
    cert = deliver.certificate(run, {"javaConversion": {"mainClass": "Prog"}}, report, program, "c0ffee")
    jsonschema.validate(cert, json.loads((CONTRACTS / "certificate.schema.json").read_text()))
    assert cert["verification"]["seed"] == 4242  # a no-repair run certified on CERT_SEED, not CERT_SEED + 0 rounds
    assert cert["legacy"]["copybooks"] == ["copybooks/REC.cpy"] and cert["java"]["files"] == ["Prog.java"]


def test_pr_body_credits_the_models_not_the_coding_assistant():
    run = {"before": {"passed": 1, "total": 2}}
    cert = {"program": "P", "verification": {"passed": 2, "total": 2, "stdoutMatch": True},
            "agent": {"modelCalls": 1, "rounds": 1, "memoryLessonsUsed": 0, "estimatedCostUsd": 0.001}}
    body = deliver._pr_body({"source": {"location": "https://github.com/o/r", "commit": "a" * 40}}, [(run, cert)], [])
    assert "Muse Spark" in body and "Claude" not in body
