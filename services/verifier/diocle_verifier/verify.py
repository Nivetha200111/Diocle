"""Verify one sample: generate inputs, run both sides, diff, and build a verification report."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import REPORT_VERSION
from .codec import convert_file
from .diff import compare
from .inputs import Case, generate_cases
from .layout import load_fields, record_format, record_length
from .runners import CLOCK, Run, read_records, run_cobol, run_java, write_records

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
    golden_cases, golden_expected, golden_meta = _golden(sample_dir, meta, in_fields, out_fields)
    in_format, in_length = record_format(meta["layouts"]["input"]), record_length(in_fields)
    corpus = [Case(f"corpus-{i + 1:04d}", "corpus", r) for i, r in enumerate(
        r for path in meta.get("corpus", []) for r in read_records(sample_dir / path, in_format, in_length))]
    cases = (fixtures + golden_cases + corpus + list(extra_cases or [])
             + generate_cases(in_fields, seed=seed, random_count=random_count))
    with tempfile.TemporaryDirectory(prefix="diocle-verify-") as tmp:
        work = Path(tmp)
        input_path = work / "input.dat"
        write_records(input_path, [c.record for c in cases], record_format(meta["layouts"]["input"]))
        out_format = (record_format(meta["layouts"]["output"]), record_length(out_fields))
        collation = meta.get("collation", "ascii")
        original = run_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], meta["dd"], input_path, work,
                             out_format, [sample_dir / m for m in meta.get("modules", [])], collation)
        converted = run_java(java_dir, meta["javaConversion"]["mainClass"], meta["dd"], input_path, work, out_format,
                             collation)

    results, golden_report = [], None
    if original.compiled and converted.compiled:
        results = compare(cases, original.output_lines, converted.output_lines, out_fields)
        if golden_cases:
            results, golden_report = _replay_golden(results, cases, golden_cases, golden_expected, original, converted,
                                                    out_fields, golden_meta)
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
            "collation": meta.get("collation", "ascii"),
            "golden": golden_report,
        },
    }


def _golden(sample_dir: Path, meta: dict, in_fields, out_fields):
    """Captured mainframe files (EBCDIC, fixed length), converted field by field to what GnuCOBOL reads and writes."""
    spec = meta.get("golden")
    if not spec:
        return [], [], None
    folder = sample_dir / spec.get("dir", "golden")
    codepage = spec.get("codepage", "cp037")
    inputs = convert_file((folder / spec["input"]).read_bytes(), in_fields, record_length(in_fields), codepage=codepage)
    expected = convert_file((folder / spec["expected"]).read_bytes(), out_fields, record_length(out_fields),
                            codepage=codepage)
    cases = [Case(f"golden-{i + 1:04d}", "golden", r.decode("latin-1")) for i, r in enumerate(inputs)]
    return cases, [r.decode("latin-1") for r in expected], spec


def _replay_golden(results, cases, golden_cases, expected, original, converted, out_fields, spec):
    """On golden inputs the mainframe's captured output is the oracle; also report whether GnuCOBOL agreed with it."""
    first = cases.index(golden_cases[0])
    agreement, disagreements = 0, []
    for k, case in enumerate(golden_cases):
        i = first + k
        if k >= len(expected):
            break
        [vs_mainframe] = compare([case], [expected[k]], converted.output_lines[i : i + 1], out_fields)
        results[i] = {**vs_mainframe, "oracle": "mainframe"}
        [oracle_check] = compare([case], [expected[k]], original.output_lines[i : i + 1], out_fields)
        if oracle_check["match"]:
            agreement += 1
        else:
            disagreements.append({"inputId": case.id, "diff": oracle_check.get("diff", "")})
    report = {"cases": len(golden_cases), "codepage": spec.get("codepage", "cp037"), "source": spec.get("source", ""),
              "oracleAgreement": agreement, "oracleDisagreements": disagreements[:10]}
    return results, report


def passes(report: dict) -> bool:
    """The one definition of equivalence: both built, same exit code (RETURN-CODE), every record and stdout equal."""
    runs, s = report["runs"], report["summary"]
    return bool(runs["original"]["compiled"] and runs["converted"]["compiled"] and runs.get("exitCodeMatch")
                and s["total"] > 0 and s["failed"] == 0 and runs["stdoutMatch"])


def validate_report(report: dict) -> None:
    import jsonschema

    jsonschema.validate(report, json.loads(CONTRACT.read_text()))
