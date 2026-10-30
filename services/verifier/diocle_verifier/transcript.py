"""The two gates of the printout intake that BUILD or RUN a transcription, kept in the verifier so they can run inside the sandbox.

`compile_check` (cobc -fsyntax-only with the verification flags) and `differential` (the original and the transcription
compiled with GnuCOBOL and run on the same generated inputs) were written for the converter's vision intake
(services/converter/diocle_converter/vision.py, which imports them from here). The public "Read a printout" button
must never run model-written COBOL beside the secrets, so `transcript_job` is what the sandbox container runs for
POST /transcript, and `remote_check` / `remote_differential` (sandbox.py) are the matching client calls.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DIFF_INPUTS = 1000  # random inputs on top of the verifier's fixture and boundary cases
DIFF_SEED = 1026


def own_diagnostics(raw: str, file_name: str, max_lines: int = 20, max_chars: int = 1500) -> str:
    """Only `<file_name>:N: error: <message>` lines about the transcription's own file survive; every other line (other
    files, echoed source context, notes) is dropped and quoted text is masked, so a file the compiler happened to read can
    never leak through the errors into the record or the retry prompt."""
    keep = []
    pattern = re.compile(r"^(?:\S*/)?" + re.escape(file_name) + r":(\d+): error: (.*)$")
    for line in raw.splitlines():
        m = pattern.match(line.strip())
        if m:
            msg = re.sub(r"'[^']*'|\"[^\"]*\"", "<text>", m.group(2))
            keep.append(f"{file_name}:{m.group(1)}: error: {msg}")
    if not keep:
        return "cobc rejected the source (no diagnostics about the transcription itself were kept)"
    return "\n".join(keep[:max_lines])[:max_chars]


def compile_check(source: Path, copybook_dir: Path | None, timeout: int = 60) -> dict:
    """cobc -fsyntax-only with the verifier's flags. {"ok": bool, "errors": str}"""
    try:
        from .runners import IBM_FLAGS, _exec
    except ImportError:
        raise
    cmd = ["cobc", "-fsyntax-only", "-std=ibm", *IBM_FLAGS]
    if copybook_dir and copybook_dir.is_dir():
        cmd += ["-I", str(copybook_dir)]
    try:
        proc = _exec(cmd + [str(source)], timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "errors": "cobc (GnuCOBOL) is not installed"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "errors": f"cobc did not finish within {timeout} s"}
    return {"ok": proc.returncode == 0, "errors": "" if proc.returncode == 0 else own_diagnostics(proc.stderr + "\n" + proc.stdout, source.name)}


def sandbox_profile(work: Path, exe: Path) -> str:
    """macOS sandbox-exec profile for the transcription's executable: no network, no file writes outside its own work
    directory (plus /dev/null and the tty), no exec of anything but the executable itself. Reads stay open (the GnuCOBOL
    runtime libraries live all over the disk). Defense in depth only; see the README for what it does not cover."""
    for path in (work, exe):
        if '"' in str(path) or "\\" in str(path):
            raise ValueError("unsafe path for a sandbox profile")
    return ("(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n"
            f'(allow file-write* (subpath "{work}") (literal "/dev/null") (literal "/dev/dtracehelper") (literal "/dev/tty"))\n'
            f'(deny process-exec*)\n(allow process-exec (literal "{exe}"))\n')


def sandbox_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def differential(against: Path, source: Path, *, random_count: int = DIFF_INPUTS, seed: int = DIFF_SEED,
                 timeout: int = 120, sandbox: bool = True) -> dict:
    """Run the original (against/sample.json's source) and the transcription on the same generated inputs; compare the
    whole output sequence, stdout and exit code. Uses the verifier's generator, builder and comparator.
    WARNING: this builds and RUNS the transcription (model-written COBOL) on this machine with plain subprocesses. On
    macOS the transcription's executable additionally runs under sandbox-exec (`sandbox`), elsewhere there is no sandbox.
    Only for our own synthetic printouts on a dev machine, and only when the caller opted in (transcribe's run_model_code).
    Each program run is limited to `timeout` seconds. A single-file program with no output layout is compared on stdout
    and exit code."""
    from .diff import compare
    from .inputs import Case, generate_cases
    from .layout import load_fields, record_format, record_length
    from .multi import is_multi
    from .runners import CLOCK_ENV, Run, _exec, build_cobol, read_records, write_records

    rec = {"against": str(against), "ran": False, "seed": seed, "inputs": 0, "matched": 0, "mismatched": 0}
    meta = json.loads((against / "sample.json").read_text())
    if "files" in meta:  # the analyzer's file list: one input and no output file is a DISPLAY-only program
        ins = [f for f in meta["files"] if f["direction"] == "input"]
        if len(ins) != 1 or len(ins) != len(meta["files"]):
            return {**rec, "reason": "only programs with one input file (and at most DISPLAY output) are supported"}
        layouts, dd = {"input": ins[0]["layout"]}, {"input": ins[0]["dd"]}
    elif is_multi(meta):
        return {**rec, "reason": "multi-file programs are not supported by the transcription differential"}
    else:
        layouts, dd = meta["layouts"], meta["dd"]
    has_out = "output" in layouts and "output" in dd
    in_fields = load_fields(layouts["input"])
    out_fields = load_fields(layouts["output"]) if has_out else []
    fixtures = [Case(f"fixture-{c['id']}", "fixture", c["record"]) for c in meta.get("fixtureCases", [])]
    cases = fixtures + generate_cases(in_fields, seed=seed, random_count=random_count)
    in_fmt = record_format(layouts["input"])
    out_fmt = (record_format(layouts["output"]), record_length(out_fields)) if has_out else ("line", 0)
    copybooks = against / meta["copybookDir"]
    modules = [against / m for m in meta.get("modules", [])]
    collation = meta.get("collation", "ascii")
    use_sandbox = sandbox and sandbox_available()
    rec["sandbox"] = "sandbox-exec" if use_sandbox else "none"
    with tempfile.TemporaryDirectory(prefix="diocle-transcribe-") as tmp:
        tmp = Path(tmp).resolve()
        work_o, work_t = tmp / "original", tmp / "transcribed"
        work_o.mkdir(), work_t.mkdir()
        input_path = tmp / "input.dat"
        write_records(input_path, [c.record for c in cases], in_fmt)

        def run(src: Path, work: Path, label: str, sandboxed: bool) -> Run:
            cmd, failed = build_cobol(src, copybooks, work, modules, collation)
            if failed:
                return failed
            out = work / f"{label}.out"
            env = {**CLOCK_ENV, f"DD_{dd['input']}": str(input_path)}
            if has_out:
                env[f"DD_{dd['output']}"] = str(out)
            if sandboxed:
                profile = tmp / f"{label}.sb"
                profile.write_text(sandbox_profile(work, Path(cmd[0]).resolve()))
                cmd = ["sandbox-exec", "-f", str(profile), *cmd]
            proc = _exec(cmd, env=env, cwd=work, timeout=timeout)
            return Run(True, proc.returncode, proc.stdout, proc.stderr, read_records(out, *out_fmt))

        try:
            orig = run(against / meta["source"], work_o, "original", False)  # our own sample, not model output
            trans = run(source, work_t, "transcribed", use_sandbox)
        except subprocess.TimeoutExpired:
            return {**rec, "inputs": len(cases), "reason": f"a program did not finish within {timeout} s (timed out)"}
    rec["inputs"] = len(cases)
    if not orig.compiled:
        return {**rec, "reason": "the original does not compile with GnuCOBOL: " + orig.stderr.strip()[:300]}
    if not trans.compiled:
        return {**rec, "reason": "the transcription does not build: " + trans.stderr.strip()[:300]}
    stdout_compared = bool(orig.stdout.strip())
    if not orig.output_lines and not stdout_compared:
        return {**rec, "reason": "the original wrote no output records and no stdout: nothing to compare, so no proof"}
    stdout_match, exit_match = orig.stdout == trans.stdout, orig.exit_code == trans.exit_code
    identical = orig.output_lines == trans.output_lines and stdout_match and exit_match
    if has_out:
        results = compare(cases, orig.output_lines, trans.output_lines, out_fields, out_fmt[0])
        bad = [r for r in results if not r["match"]]
        matched, mismatched = len(results) - len(bad), len(bad) + (0 if stdout_match else 1) + (0 if exit_match else 1)
    else:  # no output file: the whole run is one comparison of stdout and exit code
        bad, matched, mismatched = [], (len(cases) if identical else 0), (0 if identical else 1)
    if not identical and not mismatched:  # same values, differing only in trailing blanks
        mismatched = 1
    return {**rec, "ran": True, "outputRecords": len(orig.output_lines), "stdoutCompared": stdout_compared,
            "matched": matched, "mismatched": mismatched, "stdoutMatch": stdout_match, "exitCodeMatch": exit_match,
            "firstMismatches": [{k: r.get(k) for k in ("inputId", "input", "originalOutput", "convertedOutput", "fieldDiffs")
                                 if k in r} for r in bad[:5]]}


def transcript_job(sample_dir: Path, source: Path, diff: bool) -> dict:
    """What the sandbox runs for POST /transcript: the compile gate on the transcription and, when it compiles and `diff`
    is set, the differential run against the original at sample_dir. {"compile": {...}, "differential": {...} | None}.
    Runs in a throwaway directory as an unprivileged user inside the sandbox container; never on the API host."""
    meta = json.loads((sample_dir / "sample.json").read_text())
    compiled = compile_check(source, sample_dir / meta["copybookDir"])
    result = {"compile": compiled, "differential": None}
    if diff and compiled["ok"]:
        result["differential"] = differential(sample_dir, source, sandbox=False)
    return result
