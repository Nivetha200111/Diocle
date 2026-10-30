"""run_build_check end to end through the verifier's CLI child process (real javac, no model, no network)."""
import json
import shutil

import jsonschema
import pytest

from diocle_api import deliver

pytestmark = pytest.mark.skipif(shutil.which("javac") is None or not (deliver.SERVICES / "verifier/.venv/bin/python").exists(),
                                reason="needs javac and the verifier venv")
COBOL = ("       IDENTIFICATION DIVISION.\n       PROGRAM-ID. {n}.\n       PROCEDURE DIVISION.\n           GOBACK.\n")


def delivery(tmp_path, java_a, java_b):
    repo, samples = tmp_path / "repo", tmp_path / "samples"
    delivered = []
    for name, java in (("AAA", java_a), ("BBB", java_b)):
        (repo / "programs" / name / "java").mkdir(parents=True)
        (repo / "programs" / name / "java" / f"{name.capitalize()}.java").write_text(java)
        s = samples / name.lower()
        (s / "src").mkdir(parents=True)
        (s / "src" / f"{name}.cbl").write_text(COBOL.format(n=name))
        (s / "sample.json").write_text(json.dumps({"source": f"src/{name}.cbl", "modules": [], "javaConversion": {"mainClass": name.capitalize()}}))
        delivered.append(({}, {"program": name}))
    return repo, samples, delivered


def test_the_report_lands_in_the_delivery_and_validates(tmp_path):
    repo, samples, delivered = delivery(tmp_path, "public class Aaa {}\n", "public class Bbb {}\n")
    result = deliver.run_build_check(repo, delivered, samples, {"programs": []})
    assert result["verdict"] == "pass"
    assert (repo / "build" / "BUILD-REPORT.md").read_text().startswith("# Build report: PASS")
    on_disk = json.loads((repo / "build" / "build-report.json").read_text())
    jsonschema.validate(on_disk, json.loads((deliver.REPO_ROOT / "contracts" / "build-report.schema.json").read_text()))
    assert deliver.build_summary(result)["programs"] == 2


def test_a_broken_set_fails_the_gate_with_the_exact_diagnostic(tmp_path):
    repo, samples, delivered = delivery(tmp_path, "public class Aaa {\n  void f() { Missing.go(); }\n}\n", "public class Bbb {}\n")
    result = deliver.run_build_check(repo, delivered, samples, {"programs": []})
    assert result["verdict"] == "fail"
    assert result["whole"]["compile"]["diagnostics"] == ["AAA/Aaa.java:2: error: cannot find symbol [symbol: variable Missing]"]


def test_nothing_to_check_returns_none_and_writes_nothing(tmp_path):
    assert deliver.run_build_check(tmp_path / "repo", [], tmp_path, {}) is None
    assert not (tmp_path / "repo" / "build").exists()
