"""Whole-JCL-job pipeline generation (see diocle_converter/pipeline.py): the SORT step is pure sortgen.py
output (no model call); the COBOL step reuses translate.py's existing flow unchanged (one model call,
scripted here with a test double, same pattern as test_converter.py -- no network, no credits).

The job fixture below is the REAL jobs[] entry services/analyzer's analyze() produces for
samples/account-match/jcl/QMKD010.jcl (confirmed by running the analyzer's own CLI against that sample and
copying its output verbatim -- see the comment above JOB for how to reproduce it), not an invented shape.
"""

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from openai.types.chat import ChatCompletionMessage

from diocle_converter.client import ModelClient
from diocle_converter.config import Settings
from diocle_converter.pipeline import driver_class_name, generate_pipeline
from diocle_converter.sources import Program
from diocle_converter.translate import translate
from diocle_converter.workspace import Workspace

SAMPLE = Path(__file__).resolve().parents[3] / "samples" / "account-match"

# Reproduce with: python -m diocle_analyzer samples/account-match --out report.json, then report["jobs"][0].
JOB = {
    "name": "QMKD010",
    "member": "jcl/QMKD010.jcl",
    "steps": [
        {"step": "SORT005", "proc": None, "kind": "sort", "program": "SORT",
         "dds": {"SORTIN": "QMK.PROD.TXN.DAILY", "SORTOUT": "QMK.PROD.TXN.SORTED",
                 "SYSIN": "QMK.PROD.CNTLLIB(SORTTXN)"},
         "sort": {"fields": [[1, 8, "CH", "A"]], "optionEquals": True, "unsupported": None},
         "convertibleProgram": None, "notConvertibleReason": None},
        {"step": "MTCH010", "proc": None, "kind": "cobol", "program": "ACCTMTCH",
         "dds": {"MSTIN": "QMK.PROD.ACCT.MASTER(0)", "TXNIN": "QMK.PROD.TXN.SORTED",
                 "NEWMST": "QMK.PROD.ACCT.MASTER(+1)", "EXCOUT": "QMK.PROD.TXN.EXCEPTIONS(+1)"},
         "sort": None, "convertibleProgram": True, "notConvertibleReason": None},
    ],
    "wiring": [{"fromStep": "SORT005", "fromDd": "SORTOUT", "toStep": "MTCH010", "toDd": "TXNIN",
                "dsn": "QMK.PROD.TXN.SORTED"}],
    "convertible": True, "notConvertibleReason": None,
}

requires_javac = pytest.mark.skipif(shutil.which("javac") is None, reason="javac not available")


class ScriptedSDK:
    def __init__(self, messages):
        self.script = list(messages)
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = self.script.pop(0)
        usage = SimpleNamespace(prompt_tokens=1000, completion_tokens=200,
                                prompt_tokens_details=SimpleNamespace(cached_tokens=800),
                                completion_tokens_details=SimpleNamespace(reasoning_tokens=50))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def settings(**overrides):
    base = dict(mode="hosted", base_url="http://unused", api_key="test", model="muse-spark-1.3-contributor",
                reasoning_effort="low", max_calls_per_run=10, max_calls_per_round=5, max_rounds=2)
    return Settings(**{**base, **overrides})


def _translate_acctmtch(tmp_path) -> tuple[str, Workspace]:
    """translate.py's existing flow, unchanged, scripted to return the sample's real hand-written Java
    (not model output -- this test only proves pipeline.py's wiring, translate.py has its own tests)."""
    java_source = (SAMPLE / "java-conversion" / "Acctmtch.java").read_text()
    answer = json.dumps({"mainClass": "Acctmtch", "javaSource": java_source, "notes": "test double"})
    sdk = ScriptedSDK([ChatCompletionMessage(role="assistant", content=answer)])
    workspace = Workspace(tmp_path / "java")
    result = translate(Program.load(SAMPLE), ModelClient(settings(), _sdk=sdk), workspace)
    return result["mainClass"], workspace


def test_driver_class_name_capitalizes_the_job_name():
    assert driver_class_name("QMKD010") == "Qmkd010Driver"


def test_generate_pipeline_rejects_a_non_convertible_job():
    with pytest.raises(ValueError, match="not convertible"):
        generate_pipeline({**JOB, "convertible": False, "notConvertibleReason": "nope"},
                          cobol_main_class="X", record_lengths={}, collation="ascii",
                          out_dir=Path("/tmp/unused"), dd_paths={})


def test_generate_pipeline_wires_sort_output_to_the_cobol_step_input(tmp_path):
    cobol_main_class, _ = _translate_acctmtch(tmp_path)
    out_dir = tmp_path / "job"
    manifest = generate_pipeline(
        JOB, cobol_main_class=cobol_main_class, record_lengths={"SORTIN": 19, "SORTOUT": 19, "TXNIN": 19},
        collation="ebcdic", out_dir=out_dir,
        dd_paths={"SORTIN": str(tmp_path / "SORTIN.txt"), "MSTIN": str(tmp_path / "MSTIN.txt"),
                 "NEWMST": str(tmp_path / "NEWMST.out"), "EXCOUT": str(tmp_path / "EXCOUT.out")},
    )
    # Manifest shape matches contracts/conversion-output.schema.json's jobPipelines[] entry exactly.
    assert manifest["job"] == "QMKD010"
    assert manifest["driverClass"] == "Qmkd010Driver"
    assert manifest["path"] == str(out_dir)
    steps = {s["step"]: s for s in manifest["steps"]}
    assert steps["SORT005"]["kind"] == "sort" and steps["SORT005"]["origin"] == "deterministic"
    assert steps["MTCH010"]["kind"] == "cobol" and steps["MTCH010"]["origin"] == "model"
    assert steps["MTCH010"]["mainClass"] == cobol_main_class
    # The wiring: SORT005's SORTOUT and MTCH010's TXNIN point at the exact same generated file.
    assert steps["SORT005"]["dd"]["SORTOUT"] == steps["MTCH010"]["dd"]["TXNIN"]
    assert steps["SORT005"]["dd"]["SORTIN"] == str(tmp_path / "SORTIN.txt")  # untouched external input
    assert steps["MTCH010"]["dd"]["MSTIN"] == str(tmp_path / "MSTIN.txt")
    assert (out_dir / f"{steps['SORT005']['mainClass']}.java").exists()
    assert (out_dir / "Qmkd010Driver.java").exists()


def test_generate_pipeline_rejects_mismatched_sortin_sortout_lengths(tmp_path):
    with pytest.raises(ValueError, match="disagree"):
        generate_pipeline(JOB, cobol_main_class="Acctmtch", record_lengths={"SORTIN": 19, "SORTOUT": 24, "TXNIN": 24},
                          collation="ebcdic", out_dir=tmp_path / "job",
                          dd_paths={"SORTIN": "x", "MSTIN": "y", "NEWMST": "z", "EXCOUT": "w"})


@requires_javac
def test_full_pipeline_compiles_and_the_driver_runs_the_real_fixture_end_to_end(tmp_path):
    """Generates every .java file for the QMKD010 job (SORT005 deterministic, MTCH010 from a scripted
    model response using the sample's real Java), compiles all of it, and runs the driver against the
    real samples/account-match/jcl/SORTIN.txt and sample.json's seeded MSTIN fixtureFiles -- proving the
    driver actually sequences steps and wires DDs correctly, not just that it compiles."""
    cobol_main_class, workspace = _translate_acctmtch(tmp_path)
    out_dir = tmp_path / "job"
    meta = json.loads((SAMPLE / "sample.json").read_text())

    mstin_path = tmp_path / "MSTIN.in"
    mstin_path.write_text("".join(r + "\n" for r in meta["fixtureFiles"]["MSTIN"]))
    newmst_path, excout_path = tmp_path / "NEWMST.out", tmp_path / "EXCOUT.out"

    manifest = generate_pipeline(
        JOB, cobol_main_class=cobol_main_class, record_lengths={"SORTIN": 19, "SORTOUT": 19, "TXNIN": 19},
        collation="ebcdic", out_dir=out_dir,
        dd_paths={"SORTIN": str(SAMPLE / "jcl" / "SORTIN.txt"), "MSTIN": str(mstin_path),
                 "NEWMST": str(newmst_path), "EXCOUT": str(excout_path)},
    )

    classes = tmp_path / "classes"
    classes.mkdir()
    sources = [str(p) for p in workspace.root.glob("*.java")] + [str(p) for p in out_dir.glob("*.java")]
    compile_proc = subprocess.run(["javac", "-d", str(classes), *sources], capture_output=True, text=True)
    assert compile_proc.returncode == 0, compile_proc.stderr

    run_proc = subprocess.run(["java", "-cp", str(classes), manifest["driverClass"], str(classes)],
                              capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert run_proc.returncode == 0, run_proc.stderr
    assert "all steps completed" in run_proc.stdout

    sort_out_path = steps_dd(manifest, "SORT005", "SORTOUT")
    sorted_txns = Path(sort_out_path).read_text().splitlines()
    assert sorted_txns == ["A0000001+000000500C", "A0000002+000001000C", "10000001+000000100D"]  # EBCDIC order

    new_master = newmst_path.read_text().splitlines()
    exceptions = excout_path.read_text().splitlines()
    assert "A0000001+00000010500ACTV0001" in new_master  # credited: 100.00 + 5.00 = 105.00, 1 txn applied
    assert any("FROZEN" in line for line in exceptions)  # A0000002 is FRZN: its credit is rejected
    assert any("NO ACCOUNT" in line for line in exceptions)  # 10000001 has no matching master


def steps_dd(manifest: dict, step: str, dd: str) -> str:
    return next(s["dd"][dd] for s in manifest["steps"] if s["step"] == step)
