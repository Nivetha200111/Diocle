"""Verify one sample: generate inputs, run both sides, diff, and build a verification report."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import REPORT_VERSION
from .diff import compare
from .inputs import Case, generate_cases
from .layout import load_fields
from .runners import CLOCK, Run, run_cobol, run_java

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "verification-report.schema.json"


def _run_meta(run: Run) -> dict:
    return {"compiled": run.compiled, "exitCode": run.exit_code, "stdout": run.stdout, "stderr": run.stderr}


def verify_sample(sample_dir: Path, java_dir: Path | None = None, *, seed: int = 1026, random_count: int = 200,
                  extra_cases: list[Case] | None = None) -> dict:
    """extra_cases (e.g. inputs designed by a model, source "model") run before the generated ones."""
    sample_dir = sample_dir.resolve()
    meta = json.loads((sample_dir / "sample.json").read_text())
    in_fields = load_fields(meta["layouts"]["input"])
    out_fields = load_fields(meta["layouts"]["output"])
    java_dir = (java_dir or sample_dir / meta["javaConversion"]["dir"]).resolve()

    fixtures = [Case(f"fixture-{c['id']}", "fixture", c["record"]) for c in meta.get("fixtureCases", [])]
    cases = fixtures + list(extra_cases or []) + generate_cases(in_fields, seed=seed, random_count=random_count)
    with tempfile.TemporaryDirectory(prefix="diocle-verify-") as tmp:
        work = Path(tmp)
        input_path = work / "input.dat"
        input_path.write_text("".join(c.record + "\n" for c in cases))
        original = run_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], meta["dd"], input_path, work)
        converted = run_java(java_dir, meta["javaConversion"]["mainClass"], meta["dd"], input_path, work)

    results = []
    if original.compiled and converted.compiled:
        results = compare(cases, original.output_lines, converted.output_lines, out_fields)
        for r in results:
            r["program"] = meta["program"]
    passed = sum(r["match"] for r in results)
    return {
        "version": REPORT_VERSION,
        "results": results,
        "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
        "runs": {
            "original": _run_meta(original),
            "converted": _run_meta(converted),
            "stdoutMatch": original.stdout == converted.stdout,
            "exitCodeMatch": original.compiled and converted.compiled and original.exit_code == converted.exit_code,
            "clock": CLOCK,
        },
    }


def passes(report: dict) -> bool:
    """The one definition of equivalence: both built, same exit code (RETURN-CODE), every record and stdout equal."""
    runs, s = report["runs"], report["summary"]
    return bool(runs["original"]["compiled"] and runs["converted"]["compiled"] and runs.get("exitCodeMatch")
                and s["total"] > 0 and s["failed"] == 0 and runs["stdoutMatch"])


def validate_report(report: dict) -> None:
    import jsonschema

    jsonschema.validate(report, json.loads(CONTRACT.read_text()))
