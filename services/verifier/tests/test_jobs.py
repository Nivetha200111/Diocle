"""Whole-JCL-job differential testing (v1 scope: one SORT step feeding one COBOL step).

The job[] fixture is the real jobs[] entry services/analyzer's analyze() produces for
samples/account-match/jcl/QMKD010.jcl (read directly below, not hand-typed) and the pipeline[] fixture is
the real jobPipelines[] entry diocle_converter.pipeline.generate_pipeline() produces for the same job
(generated via a subprocess into services/converter's own venv -- the same read-only cross-service hand-off
convention diocle_converter's own __main__._analyzer_jobs() uses for the analyzer, kept symmetric here so
this test never imports diocle_converter directly from the verifier's package).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from diocle_analyzer.analyze import analyze
from diocle_verifier.jobs import verify_job
from diocle_verifier.verify import validate_report

ROOT = Path(__file__).resolve().parents[3]
SAMPLE = ROOT / "samples" / "account-match"
CONVERTER_PYTHON = ROOT / "services" / "converter" / ".venv" / "bin" / "python"
# A faithful Java port of samples/account-match/src/ACCTMTCH.cbl already exists in this repo (used to prove
# multi-file verification): respects DIOCLE_COLLATION and propagates RETURN-CODE via System.exit(). The
# sample's own java-conversion/Acctmtch.java is a DELIBERATELY naive fixture (ASCII key compare, no exit
# code -- see its own header comment); using it here would make the positive end-to-end test fail for
# reasons this job verifier does not exist to catch (that is the single-program verifier's job, and it
# already does catch them: see test_called_modules.py-style single-program coverage elsewhere).
FAITHFUL_ACCTMTCH = Path(__file__).resolve().parent / "fixtures" / "reference" / "Acctmtch.java"

requires_toolchain = pytest.mark.skipif(
    shutil.which("cobc") is None or shutil.which("javac") is None or not CONVERTER_PYTHON.exists(),
    reason="needs GnuCOBOL, a JDK, and services/converter's venv",
)

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "verification-report.schema.json"


def _job() -> dict:
    report = analyze(SAMPLE)
    [job] = [j for j in report["jobs"] if j["convertible"]]
    return job


_GENERATE_SCRIPT = """
import json, sys
sys.path.insert(0, {converter_src!r})
from pathlib import Path
from diocle_converter.pipeline import generate_pipeline

job = json.loads(Path({job_path!r}).read_text())
manifest = generate_pipeline(
    job, cobol_main_class={main_class!r}, record_lengths={record_lengths!r}, collation={collation!r},
    out_dir=Path({out_dir!r}), dd_paths={dd_paths!r},
)
print(json.dumps(manifest))
"""


def _generate_pipeline(job: dict, out_dir: Path, dd_paths: dict[str, str], java_source: str | None = None) -> dict:
    """Generate the real job pipeline (SORT005 deterministic, MTCH010's main class pointed at the sample's
    own hand-written Java fixture -- origin "model" per the manifest shape, but no model call is made here;
    translate.py's own tests already cover the model call itself) via diocle_converter's own venv, exactly
    the deterministic generation diocle_converter.__main__._run_job performs, called as a subprocess so this
    test never imports diocle_converter from the verifier's package (see module docstring)."""
    job_path = out_dir.parent / "job.json"
    job_path.write_text(json.dumps(job))
    script = _GENERATE_SCRIPT.format(
        converter_src=str(ROOT / "services" / "converter"), job_path=str(job_path), main_class="Acctmtch",
        record_lengths={"SORTIN": 19, "SORTOUT": 19, "TXNIN": 19}, collation="ebcdic", out_dir=str(out_dir),
        dd_paths=dd_paths,
    )
    proc = subprocess.run([str(CONVERTER_PYTHON), "-c", script], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    manifest = json.loads(proc.stdout)
    acctmtch_java = java_source or FAITHFUL_ACCTMTCH.read_text()
    (out_dir / "Acctmtch.java").write_text(acctmtch_java)
    return manifest


@requires_toolchain
def test_verify_job_end_to_end_certifies_the_real_account_match_job(tmp_path):
    """Positive, end-to-end: seed SORTIN only, run both sides, every output dataset (SORTOUT, NEWMST,
    EXCOUT) matches byte for byte, and the job is certified."""
    job = _job()
    out_dir = tmp_path / "job"
    dd_paths = {
        "SORTIN": str(tmp_path / "SORTIN.seed"),  # overwritten by verify_job's own seeding before the run
        "MSTIN": str(tmp_path / "MSTIN.seed"),
        "NEWMST": str(tmp_path / "NEWMST.out"),
        "EXCOUT": str(tmp_path / "EXCOUT.out"),
    }
    pipeline = _generate_pipeline(job, out_dir, dd_paths)

    report = {"jobs": [verify_job(SAMPLE, job, pipeline, seed=4242, random_count=5)["jobs"][0]],
              "version": "0.7", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0}}
    validate_report(report)
    [result] = report["jobs"]

    assert result["job"] == "QMKD010"
    steps = {s["step"]: s for s in result["steps"]}
    assert steps["SORT005"]["outputDds"] == ["SORTOUT"]
    assert set(steps["MTCH010"]["outputDds"]) == {"NEWMST", "EXCOUT"}
    assert steps["SORT005"]["passed"] and steps["MTCH010"]["passed"]
    assert result["summary"]["failed"] == 0 and result["summary"]["total"] > 0
    assert result["certified"] is True
    assert result["runs"]["exitCodeMatch"] is True
    assert result["runs"]["original"]["compiled"] and result["runs"]["converted"]["compiled"]
    # Every result is tagged with which step it came from (the "one certificate per job" promise: a reader
    # can tell exactly which step/DD failed, not just that something somewhere did).
    assert all("step" in r and "outputDd" in r for r in result["results"])


@requires_toolchain
def test_verify_job_reports_certified_false_with_a_named_failing_step_when_broken(tmp_path):
    """Negative, critical: corrupt the generated SORT step's class so it writes a wrong value in one field.
    The job must report certified: false with SORT005 (not MTCH010) named as the failing step."""
    job = _job()
    out_dir = tmp_path / "job"
    dd_paths = {
        "SORTIN": str(tmp_path / "SORTIN.seed"),
        "MSTIN": str(tmp_path / "MSTIN.seed"),
        "NEWMST": str(tmp_path / "NEWMST.out"),
        "EXCOUT": str(tmp_path / "EXCOUT.out"),
    }
    pipeline = _generate_pipeline(job, out_dir, dd_paths)

    # Corrupt the generated SORT class: flip ascending to descending, so SORTOUT comes out backwards.
    sort_file = next(out_dir.glob("*Sort005.java"))
    source = sort_file.read_text()
    assert "(a, b) -> DiocleSort.compareKeyBytes" in source
    corrupted = source.replace(
        "(a, b) -> DiocleSort.compareKeyBytes", "(a, b) -> -DiocleSort.compareKeyBytes", 1
    )
    assert corrupted != source
    sort_file.write_text(corrupted)

    report = verify_job(SAMPLE, job, pipeline, seed=4242, random_count=5)
    [result] = report["jobs"]

    assert result["certified"] is False
    steps = {s["step"]: s for s in result["steps"]}
    assert steps["SORT005"]["passed"] is False  # the corrupted step is named
    assert steps["MTCH010"]["passed"] is False  # and the downstream step it feeds also fails, as expected
    failing_dds = {r["outputDd"] for r in result["results"] if not r["match"]}
    assert "SORTOUT" in failing_dds  # the SORT step's own output already disagrees, named specifically


@requires_toolchain
def test_verify_job_report_validates_against_the_contract(tmp_path):
    job = _job()
    out_dir = tmp_path / "job"
    dd_paths = {
        "SORTIN": str(tmp_path / "SORTIN.seed"), "MSTIN": str(tmp_path / "MSTIN.seed"),
        "NEWMST": str(tmp_path / "NEWMST.out"), "EXCOUT": str(tmp_path / "EXCOUT.out"),
    }
    pipeline = _generate_pipeline(job, out_dir, dd_paths)
    job_result = verify_job(SAMPLE, job, pipeline, seed=1, random_count=3)["jobs"][0]
    full_report = {"version": "0.7", "results": [], "summary": {"total": 0, "passed": 0, "failed": 0},
                  "jobs": [job_result]}
    import jsonschema
    jsonschema.validate(full_report, json.loads(CONTRACT.read_text()))
