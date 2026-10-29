"""Whole-JCL-job differential testing (v1 scope: one SORT step feeding one COBOL step).

Consumes the analyzer's `jobs[]` entry (services/analyzer/diocle_analyzer/jcl.py's Job/SortSpec, as emitted
by analyze()) and the converter's matching `jobPipelines[]` entry (services/converter/diocle_converter/pipeline.py's
generate_pipeline()), exactly as those two modules already shape them -- this module does not reimplement
either side's generation logic, only runs and compares what they already produced.

"Original" side: the job's one kind:"cobol" step is compiled with the existing GnuCOBOL build path
(runners.build_cobol, unchanged). The kind:"sort" step has no original executable to run (DFSORT/SORT is a
mainframe utility, not something this project compiles): its reference behaviour is the same byte-collation
sort key convention this codebase already uses everywhere else to decide order -- multi.py's own
_sort_key() -- applied to the SortSpec's fields, imported and called directly, never reimplemented, so the
reference SORT and the converter's generated SORT (sortgen.py) are provably using identical byte collation.
Steps run in job order in a per-job temp working directory; each step's output file becomes the next step's
input file on disk exactly per the job's wiring[] edges (same as the real JCL job would hand datasets
between steps), not by re-deriving the output in memory.

"Converted" side: the generated job pipeline directory (all its .java files) is compiled once with javac,
then the driver class's main() is run once end to end via subprocess, exactly as
services/converter/tests/test_pipeline.py's own end-to-end test does (java -cp <classes> <driverClass>
<classes>), matching that pattern so this harness never second-guesses how the generated driver is invoked.

Seeding: only the job's true external inputs are seeded -- DDs some step consumes but no step in the same
job produces (no incoming wiring[] edge). For this v1 shape that is SORTIN alone; generate_cases() (the same
boundary + seeded-random case generator every other sample uses) seeds it. SORTOUT and TXNIN are never
seeded directly: they are produced by actually running the SORT step and wiring its output to the COBOL
step's input, which is what proves the hand-off between steps, not just each step in isolation. Any other DD
the COBOL step reads that is not fed by this job's wiring (e.g. MSTIN, the account master) is seeded from
the sample's own fixtureFiles, the same per-DD seed records single-program verification already uses for it.

Comparison: diff.py's compare() is called once per (step, output DD) pair, unchanged -- it is already
position-based and byte-for-byte, dataset-shaped rather than program-shaped, so no new comparison logic is
needed here, only a loop tagging each result with which step and DD it came from.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .diff import compare
from .inputs import Case, generate_cases
from .layout import load_fields, record_format, record_length
from .multi import _sort_key
from .runners import CLOCK, CLOCK_ENV, Run, _exec, build_cobol, read_records, safe_env, write_records


def _seed_free_dds(job: dict) -> set[str]:
    """DDs some step reads that no step in this job writes (no incoming wiring[] edge): the job's true
    external inputs. For the v1 SORT-then-COBOL shape that is SORTIN alone."""
    produced_by_step = {(e["toStep"], e["toDd"]) for e in job.get("wiring", [])}
    external = set()
    for step in job["steps"]:
        for dd in step["dds"]:
            if dd in ("SYSIN", "SYSOUT"):
                continue
            if (step["step"], dd) in produced_by_step:
                continue
            external.add(dd)
    return external


def _sort_reference(records: list[str], spec: dict, collation: str) -> list[str]:
    """The reference SORT step's behaviour: a stable sort (Python's list.sort is a stable Timsort, same
    guarantee the converter's sortgen.py relies on for Collections.sort, so OPTION EQUALS holds for free)
    keyed on multi.py's own _sort_key() applied to each field in SortSpec.fields, major key first.

    SortSpec.fields entries are 1-based (start, length, format, "A"|"D") tuples (jcl.py's SortSpec, v1 scope:
    CH/ZD/PD/BI). v1 ships only CH fixtures; ZD/PD/BI keys are read as their raw character bytes here too
    (same _sort_key() byte-collation call sortgen.py's compareUnsignedDigits documents as v1 scope for those
    formats -- a real packed/binary decode is future work on both sides, not reimplemented differently here).
    """
    fields = spec["fields"]

    def key(record: str) -> tuple:
        parts = []
        for start, length, _fmt, order in fields:
            chunk = record[start - 1 : start - 1 + length]
            encoded = _sort_key(chunk, collation)
            parts.append(encoded if order == "A" else tuple(-b for b in encoded))
        return tuple(parts)

    return sorted(records, key=key)


def _run_meta(run: Run) -> dict:
    return {"compiled": run.compiled, "exitCode": run.exit_code, "stdout": run.stdout, "stderr": run.stderr}


def _run_original(sample_dir: Path, job: dict, dd_paths: dict[str, Path], work: Path) -> dict:
    """Run every step of the job on the "original" side in job order, writing each step's output to the
    path that is the next step's input per job["wiring"]. Returns {dd: records} for every output DD, plus
    the cobol step's Run (compile/exit/stdout/stderr) for the report's runs.original."""
    meta = json.loads((sample_dir / "sample.json").read_text())
    collation = meta.get("collation", "ascii")
    outputs: dict[str, list[str]] = {}
    cobol_run: Run | None = None
    cobol_cmd: list[str] | None = None
    build_failure: Run | None = None

    for step in job["steps"]:
        if step["kind"] == "sort":
            # Same SORTIN/SORTOUT-by-convention-else-DD-statement-order rule diocle_converter.pipeline uses
            # (see pipeline.py's generate_pipeline()), so both sides agree on which DD is which.
            data_dds = [d for d in step["dds"] if d not in ("SYSIN", "SYSOUT")]
            in_dd = "SORTIN" if "SORTIN" in step["dds"] else data_dds[0]
            out_edges = [e for e in job["wiring"] if e["fromStep"] == step["step"]]
            out_dd = out_edges[0]["fromDd"] if out_edges else (
                "SORTOUT" if "SORTOUT" in step["dds"] else data_dds[1])
            records = read_records(dd_paths[(step["step"], in_dd)], "line", 0)
            sorted_records = _sort_reference(records, step["sort"], collation)
            outputs[out_dd] = sorted_records
            write_records(dd_paths[(step["step"], out_dd)], sorted_records, "line")
        elif step["kind"] == "cobol":
            out_fields = {f["dd"]: load_fields(f["layout"]) for f in meta["files"] if f["direction"] == "output"}
            cobol_cmd, build_failure = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"],
                                                   work, [sample_dir / m for m in meta.get("modules", [])], collation)
            if cobol_cmd is None:
                cobol_run = build_failure
                break
            env = {f"DD_{dd}": str(dd_paths[(step["step"], dd)]) for dd in step["dds"]
                   if dd not in ("SYSIN", "SYSOUT")}
            proc = _exec(cobol_cmd, env={**CLOCK_ENV, **env}, cwd=work)
            cobol_run = Run(True, proc.returncode, proc.stdout, proc.stderr)
            for f in meta["files"]:
                if f["direction"] == "output":
                    fmt = record_format(f["layout"])
                    outputs[f["dd"]] = read_records(dd_paths[(step["step"], f["dd"])], fmt,
                                                     record_length(out_fields[f["dd"]]))
        else:
            raise ValueError(f"step {step['step']}: kind {step['kind']!r} is not supported by the job verifier")

    if cobol_run is None:
        cobol_run = Run(False, None, "", "no kind:\"cobol\" step ran")
    return {"outputs": outputs, "cobolRun": cobol_run}


def _pipeline_dd_paths(pipeline: dict) -> dict[tuple[str, str], str]:
    """(step, dd) -> file path for every DD the generated pipeline binds. These paths are baked into the
    generated driver source at generation time (diocle_converter.pipeline.generate_pipeline()'s dd_paths
    parameter), so this verifier must write seeded external inputs to these exact paths, not paths of its
    own choosing: the driver's main() has no way to take a path override at run time."""
    paths: dict[tuple[str, str], str] = {}
    for step in pipeline["steps"]:
        for dd, path in step["dd"].items():
            paths[(step["step"], dd)] = path
    return paths


def _run_converted(pipeline: dict, work: Path, collation: str) -> dict:
    """Compile the generated job pipeline directory once, then run its driver class's main() once end to
    end via subprocess, exactly as services/converter/tests/test_pipeline.py's own end-to-end test does.
    DIOCLE_COLLATION is set on the driver's own process (not per-step): ProcessBuilder.environment() starts
    as a copy of its parent's environment before the driver's own DD_<name> overrides are applied, so each
    step subprocess inherits it automatically -- the same convention runners.run_java() already uses for
    single-program verification."""
    pipeline_dir = Path(pipeline["path"])
    classes = work / "classes"
    classes.mkdir(exist_ok=True)
    sources = sorted(str(p) for p in pipeline_dir.glob("*.java"))
    build = subprocess.run(["javac", "-d", str(classes), *sources], env=safe_env(), capture_output=True, text=True)
    if build.returncode != 0:
        return {"run": Run(False, build.returncode, build.stdout, build.stderr), "outputs": {}}

    proc = subprocess.run(["java", "-cp", str(classes), pipeline["driverClass"], str(classes)],
                          env=safe_env({**CLOCK_ENV, "DIOCLE_COLLATION": collation.upper()}),
                          cwd=work, capture_output=True, text=True)
    run = Run(True, proc.returncode, proc.stdout, proc.stderr)

    outputs: dict[str, dict] = {}  # step -> {dd: path}
    for step in pipeline["steps"]:
        outputs[step["step"]] = step["dd"]
    return {"run": run, "outputs": outputs}


def _output_dd_specs(job: dict, meta: dict, layout_by_dd: dict[str, dict]) -> list[tuple[str, str, dict | None]]:
    """(step, dd, layout-or-None) for every output-role DD on every step: SORT steps' SORTOUT-equivalent dd
    (whichever DD the step writes per job["wiring"], or the second non-SYSIN/SYSOUT dd if it feeds no later
    step), using the layout forwarded onto it by verify_job's own wiring/SORT-pair propagation (so its
    record length is known and compare() does not mistake "no layout" for "zero-length record"); and every
    kind:"cobol" step's output-direction DDs from sample.json's files[]."""
    by_dd_layout = {f["dd"]: f["layout"] for f in meta["files"] if f["direction"] == "output"}
    specs: list[tuple[str, str, dict | None]] = []
    for step in job["steps"]:
        if step["kind"] == "sort":
            out_edges = [e for e in job["wiring"] if e["fromStep"] == step["step"]]
            data_dds = [d for d in step["dds"] if d not in ("SYSIN", "SYSOUT")]
            out_dd = out_edges[0]["fromDd"] if out_edges else (data_dds[1] if len(data_dds) > 1 else data_dds[0])
            specs.append((step["step"], out_dd, layout_by_dd.get(out_dd)))
        elif step["kind"] == "cobol":
            for dd in step["dds"]:
                if dd in by_dd_layout:
                    specs.append((step["step"], dd, by_dd_layout[dd]))
    return specs


def verify_job(sample_dir: Path, job: dict, pipeline: dict, seed: int = 1026, random_count: int = 200) -> dict:
    """Whole-job differential test: run both sides end to end on the same seeded external inputs, compare
    every step's output DD. job: one analyzer jobs[] entry. pipeline: the converter's matching jobPipelines[]
    entry (its "path" must point at the generated .java files, its "dd" per step must point at real files on
    disk already -- see diocle_converter.pipeline.generate_pipeline())."""
    from . import REPORT_VERSION

    sample_dir = sample_dir.resolve()
    meta = json.loads((sample_dir / "sample.json").read_text())
    collation = meta.get("collation", "ascii")
    external_dds = _seed_free_dds(job)
    layout_by_dd = {f["dd"]: f["layout"] for f in meta["files"]}
    # A JCL-level DD with no sample.json entry (e.g. SORTIN, SORTOUT) inherits the layout of whichever
    # COBOL-side DD it eventually reaches: forward along wiring[] edges between steps, and also between a
    # SORT step's own input and output DD (SORT never reformats records in this v1 scope -- same convention
    # diocle_converter's __main__._run_job already uses for record_lengths). Iterate to a fixed point since
    # SORTIN only reaches a known layout transitively (SORTIN == SORTOUT's layout, and SORTOUT -> TXNIN via
    # wiring[] is what sample.json actually describes).
    sort_pairs = []
    for step in job["steps"]:
        if step["kind"] == "sort":
            data_dds = [d for d in step["dds"] if d not in ("SYSIN", "SYSOUT")]
            in_dd = "SORTIN" if "SORTIN" in step["dds"] else data_dds[0]
            out_edges = [e for e in job["wiring"] if e["fromStep"] == step["step"]]
            out_dd = out_edges[0]["fromDd"] if out_edges else (
                "SORTOUT" if "SORTOUT" in step["dds"] else data_dds[1])
            sort_pairs.append((in_dd, out_dd))
    for _ in range(len(job["steps"]) + 1):  # small, bounded fixed-point pass over a handful of edges
        changed = False
        for e in job.get("wiring", []):
            for a, b in ((e["fromDd"], e["toDd"]), (e["toDd"], e["fromDd"])):
                if a not in layout_by_dd and b in layout_by_dd:
                    layout_by_dd[a] = layout_by_dd[b]
                    changed = True
        for a, b in sort_pairs:
            for x, y in ((a, b), (b, a)):
                if x not in layout_by_dd and y in layout_by_dd:
                    layout_by_dd[x] = layout_by_dd[y]
                    changed = True
        if not changed:
            break

    seeded_cases: dict[str, list[Case]] = {}
    for dd in external_dds:
        if dd in meta.get("fixtureFiles", {}):
            seeded_cases[dd] = [Case(f"{dd}-fixture-{i + 1:04d}", "fixture", r)
                                 for i, r in enumerate(meta["fixtureFiles"][dd])]
        elif dd in layout_by_dd:
            seeded_cases[dd] = generate_cases(load_fields(layout_by_dd[dd]), seed=seed, random_count=random_count)
        else:
            raise ValueError(f"verify_job: DD {dd!r} is a true external input of job {job['name']!r} "
                             "but has no known layout (sample.json files[], forwarded along wiring[]) or "
                             "fixtureFiles entry to seed it from")

    pipeline_dd_paths = _pipeline_dd_paths(pipeline)

    results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="diocle-verify-job-") as tmp_o, \
         tempfile.TemporaryDirectory(prefix="diocle-verify-job-c-") as tmp_c:
        work_o, work_c = Path(tmp_o), Path(tmp_c)

        # Every DD path the original side reads/writes, by (step, dd): seeded externals get a written-out
        # file in this run's own temp dir; any internal producer->consumer edge gets one shared path (set
        # below from wiring[]) so one step's output literally becomes the next step's input on disk.
        dd_paths_o: dict[tuple[str, str], Path] = {}
        for step in job["steps"]:
            for dd in step["dds"]:
                if dd in ("SYSIN", "SYSOUT"):
                    continue
                dd_paths_o[(step["step"], dd)] = work_o / f"{step['step']}.{dd}.dat"
        for e in job["wiring"]:  # wiring edges share the exact same path on each side of the hand-off
            dd_paths_o[(e["toStep"], e["toDd"])] = dd_paths_o[(e["fromStep"], e["fromDd"])]

        # Seeded externals are written to BOTH this run's own original-side path AND the exact path the
        # generated pipeline was built with (its driver's source has that path baked in -- see
        # _pipeline_dd_paths()'s docstring -- so there is no run-time way to point it elsewhere).
        for step in job["steps"]:
            for dd in step["dds"]:
                if dd not in external_dds or dd not in seeded_cases:
                    continue
                fmt = record_format(layout_by_dd.get(dd, {"format": "line"}))
                records = [c.record for c in seeded_cases[dd]]
                write_records(dd_paths_o[(step["step"], dd)], records, fmt)
                converted_path = pipeline_dd_paths.get((step["step"], dd))
                if converted_path is None:
                    raise ValueError(f"verify_job: the generated pipeline has no path for external DD "
                                     f"{dd!r} on step {step['step']!r}; it cannot be seeded on the converted side")
                write_records(Path(converted_path), records, fmt)

        original = _run_original(sample_dir, job, dd_paths_o, work_o)
        converted = _run_converted(pipeline, work_c, collation)

        step_reports = []
        for step in job["steps"]:
            step_reports.append({"step": step["step"], "kind": step["kind"], "program": step["program"],
                                 "outputDds": [], "passed": True})
        step_by_name = {s["step"]: s for s in step_reports}

        for step_name, dd, layout in _output_dd_specs(job, meta, layout_by_dd):
            o_records = original["outputs"].get(dd, [])
            fmt = record_format(layout) if layout else "line"
            if layout:
                out_fields = load_fields(layout)
                c_path = converted["outputs"].get(step_name, {}).get(dd)
                c_records = read_records(Path(c_path), fmt, record_length(out_fields)) if c_path else []
                cases = [Case(f"{step_name}.{dd}#{i + 1:04d}", "output", "") for i in range(len(o_records))]
                dd_results = compare(cases, o_records, c_records, out_fields, fmt)
            else:  # SORT output: plain line records, no field layout -- compare whole lines
                c_path = converted["outputs"].get(step_name, {}).get(dd)
                c_records = read_records(Path(c_path), "line", 0) if c_path else []
                cases = [Case(f"{step_name}.{dd}#{i + 1:04d}", "output", "") for i in range(len(o_records))]
                dd_results = compare(cases, o_records, c_records, [], "line")
            step_passed = all(r["match"] for r in dd_results)
            step_by_name[step_name]["outputDds"].append(dd)
            step_by_name[step_name]["passed"] = step_by_name[step_name]["passed"] and step_passed
            for r in dd_results:
                r.update({"program": job["name"], "step": step_name, "outputDd": dd})
                r.pop("input", None)
                r.pop("inputSource", None)
                results.append(r)

    passed = sum(r["match"] for r in results)
    exit_match = (original["cobolRun"].compiled and converted["run"].compiled
                 and original["cobolRun"].exit_code == converted["run"].exit_code)
    all_steps_passed = all(s["passed"] for s in step_reports)
    # One certificate per job (same equivalence definition verify.py's passes() uses for a single program):
    # both sides must have compiled, every step's output DD must match byte for byte, and the job's final
    # exit code (the COBOL step's RETURN-CODE) must agree -- a step that "passes" on its output bytes but
    # disagrees on RETURN-CODE is still not certified.
    certified = bool(original["cobolRun"].compiled and converted["run"].compiled and len(results) > 0
                     and all(r["match"] for r in results) and all_steps_passed and exit_match)

    return {
        "jobs": [{
            "job": job["name"],
            "steps": step_reports,
            "results": results,
            "summary": {"total": len(results), "passed": passed, "failed": len(results) - passed},
            "runs": {
                "original": _run_meta(original["cobolRun"]),
                "converted": _run_meta(converted["run"]),
                "exitCodeMatch": exit_match,
                "clock": CLOCK,
                "collation": collation,
            },
            "certified": certified,
        }],
        "version": REPORT_VERSION,
    }
