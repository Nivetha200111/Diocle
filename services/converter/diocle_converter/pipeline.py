"""Whole-JCL-job pipeline generation: one SORT step + one COBOL step, run in job order.

Consumes a `Job`-shaped dict exactly as the analyzer's `analyze()` emits it in `jobs[]` (see
services/analyzer/diocle_analyzer/analyze.py's `_job_report()` and jcl.py's `Job`/`SortSpec`), together
with the already-translated Java for the job's one `kind: "cobol"` step (reusing translate.py's existing
single-program flow unchanged -- see __main__.py's `run-job` command). It does not call a model itself:
the only model call in a job conversion is the one COBOL-program translation, already accounted for before
this module runs. The SORT step is pure sortgen.py output (zero model calls, logged separately -- see
__main__.py's `_run_job` print of the model-call/deterministic split).

Driver generation: `generate_driver()` emits one `<Job>Driver.java` whose main() runs every step through
ProcessBuilder, in job order, wiring step N's output DD environment variable to step N+1's matching input DD
per the job's `wiring[]` entries (fromStep/fromDd -> toStep/toDd), and propagating the first non-zero exit
code immediately (fail fast: later steps never run after an earlier one failed, matching how a real JCL job
abends on a non-zero step return code by default, COND= gates aside -- out of scope for v1, same as jcl.py).

DD environment variable convention: `DD_<ddname>`, exactly as services/verifier/diocle_verifier/runners.py's
run_files()/`_run_program()` already set them for single-program verification runs (e.g. DD_SORTIN,
DD_SORTOUT, DD_MSTIN): the driver sets the same env var name per step so the step's class (whether
sortgen-produced or model-translated) needs no job-specific knowledge of its own DD names beyond what it
already expects.

File wiring: a step that is not fed by an earlier step's wiring (e.g. the job's first step's inputs, or a
DD with no in-job producer) is wired to the file path supplied by the caller for that (step, dd) -- see
`generate_pipeline()`'s `dd_paths` parameter. A later step's DD wired from an earlier step's output (per
`job["wiring"]`) is pointed at that earlier step's own output file path, which is private to the pipeline's
working directory: the job's internal dataset never needs an external DD override, matching how DISP=(NEW,...)
intermediate JCL datasets are never provided by the caller either.
"""

from __future__ import annotations

import json
from pathlib import Path

from .sortgen import generate_sort_class


def _step_main_class(step: dict, job_name: str) -> str:
    """Deterministic Java class name for a SORT step: <Job><Step>, e.g. QMKD010 + SORT005 -> Qmkd010Sort005."""
    return f"{job_name.capitalize()}{step['step'].capitalize()}"


def driver_class_name(job_name: str) -> str:
    return f"{job_name.capitalize()}Driver"


def generate_pipeline(job: dict, *, cobol_main_class: str, record_lengths: dict[str, int], collation: str,
                      out_dir: Path, dd_paths: dict[str, str]) -> dict:
    """Generate every Java file for one job and return a manifest dict (the jobPipelines[] entry shape,
    see contracts/conversion-output.schema.json).

    job: one analyzer jobs[] entry (dict, not the dataclass -- this module only reads the JSON shape).
    cobol_main_class: the main class name of the already-translated kind:"cobol" step (translate.py's
        result["mainClass"]; translation itself happens once in __main__.py, not here).
    record_lengths: {ddname: byte length} for every DD a SORT step reads or writes in this job, taken from
        the consuming/producing COBOL step's file layout (see Program.files / sample.json "files").
    dd_paths: {ddname: filepath} for every DD that is NOT produced by an earlier step in this job (i.e. the
        job's true external inputs/outputs) -- e.g. {"SORTIN": "/path/to/input", "NEWMST": "/path/to/out", ...}.
    out_dir: where the generated .java files are written.
    """
    if job.get("notConvertibleReason"):
        raise ValueError(f"job {job['name']} is not convertible: {job['notConvertibleReason']}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Internal DD -> file path for every wiring edge: the producer step's output lands in out_dir, and the
    # consumer step's matching input DD is pointed at that same path (see module docstring).
    wired_paths: dict[tuple[str, str], str] = {}
    for edge in job.get("wiring", []):
        path = str(out_dir / f"{edge['fromStep']}.{edge['fromDd']}.wired")
        wired_paths[(edge["fromStep"], edge["fromDd"])] = path
        wired_paths[(edge["toStep"], edge["toDd"])] = path

    steps_manifest = []
    for step in job["steps"]:
        # SYSIN/SYSOUT are control-statement/listing DDs, not runtime data files: SYSIN was already
        # consumed when the analyzer parsed the SORT control statement into step["sort"], and SYSOUT is
        # mainframe print output this v1 does not emulate. Neither needs a DD_<name> env var at run time.
        data_dds = [dd for dd in step["dds"] if dd not in ("SYSIN", "SYSOUT")]
        dd_map: dict[str, str] = {}
        for dd in data_dds:
            key = (step["step"], dd)
            dd_map[dd] = wired_paths.get(key) or dd_paths.get(dd)
            if dd_map[dd] is None:
                raise ValueError(f"step {step['step']}: no path known for DD {dd!r} "
                                 "(not wired from an earlier step and not in dd_paths)")
        if step["kind"] == "sort":
            main_class = _step_main_class(step, job["name"])
            # Which DD is the sort's input vs output: SORTIN/SORTOUT by DFSORT convention if present (the
            # real fixture uses exactly these names), else fall back to dds map order (JCL DD statement
            # order, which the analyzer's s.dsns dict preserves) -- the first non-SYSIN/SYSOUT DD is the
            # input, the second is the output. SYSIN/SYSOUT are control-statement/listing DDs, never data.
            data_dds = [d for d in step["dds"] if d not in ("SYSIN", "SYSOUT")]
            input_dd = "SORTIN" if "SORTIN" in step["dds"] else data_dds[0]
            output_dd = "SORTOUT" if "SORTOUT" in step["dds"] else data_dds[1]
            length_in, length_out = record_lengths.get(input_dd), record_lengths.get(output_dd)
            if length_in is not None and length_out is not None and length_in != length_out:
                raise ValueError(f"step {step['step']}: SORTIN/SORTOUT record lengths disagree "
                                 f"({length_in} vs {length_out}); OUTREC reformatting is not supported")
            length = length_out if length_out is not None else length_in
            if length is None:
                raise ValueError(f"step {step['step']}: no known record length for {input_dd!r}/{output_dd!r} "
                                 "(pass it in record_lengths, derived from the consuming COBOL step's file layout)")
            source = generate_sort_class(step["sort"], main_class, length, collation)
            (out_dir / f"{main_class}.java").write_text(source)
            steps_manifest.append({"step": step["step"], "kind": "sort", "mainClass": main_class,
                                   "origin": "deterministic", "dd": dd_map, "_argv": [input_dd, output_dd]})
        elif step["kind"] == "cobol":
            steps_manifest.append({"step": step["step"], "kind": "cobol", "mainClass": cobol_main_class,
                                   "origin": "model", "dd": dd_map, "_argv": []})
        else:
            raise ValueError(f"step {step['step']}: kind {step['kind']!r} is not convertible yet")

    driver_class = driver_class_name(job["name"])
    driver_source = generate_driver(driver_class, steps_manifest)
    (out_dir / f"{driver_class}.java").write_text(driver_source)

    return {
        "job": job["name"],
        "path": str(out_dir),
        "driverClass": driver_class,
        "steps": [{k: v for k, v in s.items() if not k.startswith("_")} for s in steps_manifest],
    }


def generate_driver(driver_class: str, steps: list[dict]) -> str:
    """Java source for <Job>Driver: runs each step's main class via ProcessBuilder, in order, with that
    step's DD_<name> env vars set, failing fast on the first non-zero exit code (see module docstring)."""
    blocks = []
    for i, step in enumerate(steps):
        env_lines = "\n".join(f'            env.put("DD_{dd}", {json.dumps(path)});' for dd, path in step["dd"].items())
        argv = ", ".join(json.dumps(a) for a in step.get("_argv", []))
        args_array = f'new String[]{{{argv}}}' if argv else "new String[0]"
        blocks.append(f'''        {{
            System.out.println("[{driver_class}] step {i + 1}/{len(steps)}: {step['step']} ({step['mainClass']}, {step['origin']})");
            List<String> cmd = new ArrayList<>(List.of("java", "-cp", classpath, "{step['mainClass']}"));
            cmd.addAll(List.of({args_array}));
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.inheritIO();
            Map<String, String> env = pb.environment();
{env_lines}
            Process proc = pb.start();
            int code = proc.waitFor();
            if (code != 0) {{
                System.err.println("[{driver_class}] step {step['step']} failed with exit code " + code + "; stopping");
                System.exit(code);
            }}
        }}''')
    body = "\n".join(blocks)
    return f'''// GENERATED by diocle_converter.pipeline -- deterministic, no model call. Do not hand-edit.
// Runs {driver_class.replace("Driver", "")}'s steps in job order via ProcessBuilder, each with its own
// DD_<name> environment variables (see diocle_verifier.runners' convention), failing fast on the first
// non-zero exit code so no later step ever runs after an earlier one failed.
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class {driver_class} {{
    public static void main(String[] args) throws Exception {{
        String classpath = args.length > 0 ? args[0] : ".";
{body}
        System.out.println("[{driver_class}] all steps completed");
    }}
}}
'''
