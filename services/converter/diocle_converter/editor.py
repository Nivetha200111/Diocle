"""Editor commands: `python -m diocle_converter editor check|convert FILE.cbl` for the VS Code extension (editors/vscode).

stdout carries exactly one JSON document (contracts/editor-result.schema.json v0.1); progress goes to stderr as
`PROGRESS <text>` lines. LOCAL use with the developer's own Meta key; nothing here talks to Diocle servers.

  check    compile the file with the verification flags (cobc -x -std=ibm + IBM_FLAGS), full diagnostics with line numbers.
  convert  build a repo-shaped copy of the file plus its copybook folders in a temp dir, run the analyzer and the existing
           `run` pipeline on it with a hard dollar cap, copy the run into <workspace>/.diocle/runs/. The record is POINTED
           AT, not re-derived: assurance, reason, cost and model are copied from run.json (run schema v0.14).
The user's file is never written to.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .config import REPO_ROOT, Settings, load_dotenv

VERSION = "0.1"
DEFAULT_MAX_USD = 0.25
HARD_MAX_USD = 1.00  # rule 10: raising this needs the owner's OK
MAX_SOURCE_BYTES = 2_000_000
MAX_COPYBOOK_FILES = 500
COMPILE_TIMEOUT = 60
RUN_TIMEOUT = 1800
COPYBOOK_SUFFIXES = {".cpy", ".copy", ".cbl", ".cob", ".cobol", ".inc", ""}
LABELS = ("certified", "certified-against-repaired-cobol", "compiled-unverified", "failed")

_DIAG = re.compile(r"^(?P<file>.+?):(?P<line>\d+): (?P<sev>error|warning|note): (?P<msg>.*)$")


def parse_diagnostics(text: str) -> list[dict]:
    """cobc prints `FILE:LINE: error: TEXT`; source-context lines are not diagnostics and are dropped."""
    out = []
    for raw in text.splitlines():
        m = _DIAG.match(raw.strip())
        if m and int(m["line"]) >= 1:
            out.append({"file": m["file"], "line": int(m["line"]), "severity": m["sev"], "message": m["msg"][:500]})
        if len(out) >= 200:
            break
    return out


def progress(text: str) -> None:
    print(f"PROGRESS {text}".rstrip()[:300], file=sys.stderr, flush=True)


def _fail(command: str, path: str, error: str, **extra) -> dict:
    return {"version": VERSION, "command": command, "ok": False, "file": path, "error": error[:500],
            **({"diagnostics": []} if command == "check" else {}), **extra}


def _ibm_flags() -> list[str]:
    try:
        from diocle_verifier.runners import IBM_FLAGS
        return list(IBM_FLAGS)
    except ImportError:  # verifier not importable: same two flags the verifier uses
        return ["-fbinary-truncate", "-fpretty-display"]


def _search_dirs(source: Path, copybooks: list[str]) -> list[Path]:
    dirs = [source.parent, *(Path(c).resolve() for c in copybooks)]
    seen, out = set(), []
    for d in dirs:
        if d.is_dir() and d not in seen:
            seen.add(d)
            out.append(d)
    return out


def check(path: str, copybooks: list[str]) -> dict:
    source = Path(path)
    if not source.is_file():
        return _fail("check", path, "file not found")
    if not shutil.which("cobc"):
        return _fail("check", path, "GnuCOBOL (cobc) is not installed or not on PATH")
    with tempfile.TemporaryDirectory(prefix="diocle-editor-") as tmp:
        cmd = ["cobc", "-x", "-std=ibm", *_ibm_flags(), *(a for d in _search_dirs(source.resolve(), copybooks) for a in ("-I", str(d))),
               "-o", str(Path(tmp) / "out"), str(source.resolve())]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=COMPILE_TIMEOUT, cwd=tmp, errors="replace")
        except subprocess.TimeoutExpired:
            return _fail("check", path, f"compiling took longer than {COMPILE_TIMEOUT} seconds")
    diags = parse_diagnostics(proc.stderr + "\n" + proc.stdout)
    result = {"version": VERSION, "command": "check", "ok": proc.returncode == 0, "file": path, "diagnostics": diags}
    if proc.returncode != 0 and not any(d["severity"] == "error" for d in diags):
        result["error"] = "the compiler failed without a diagnostic"
    return result


# ---- convert -------------------------------------------------------------------------------------------------------

def stage_repo(source: Path, copybooks: list[str], dest: Path) -> int:
    """repo-shaped copy: cobol/<file> plus every copybook-looking file of the search folders in copybooks/. Returns the count."""
    (dest / "cobol").mkdir(parents=True)
    (dest / "copybooks").mkdir()
    shutil.copy(source, dest / "cobol" / source.name)
    n = 0
    for d in _search_dirs(source, copybooks):
        suffixes = {".cpy", ".copy", ".inc"} if d == source.parent else COPYBOOK_SUFFIXES  # beside the program: copybooks only
        for f in sorted(d.iterdir()):
            if (f.is_file() and not f.is_symlink() and f.suffix.lower() in suffixes and f.resolve() != source
                    and f.stat().st_size <= 1_000_000 and not (dest / "copybooks" / f.name).exists() and n < MAX_COPYBOOK_FILES):
                shutil.copy(f, dest / "copybooks" / f.name)
                n += 1
    return n


def _python_for(service: str) -> str:
    venv = REPO_ROOT / "services" / service / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def run_analyzer(repo: Path, out: Path, convert_anyway: bool) -> dict:
    cmd = [_python_for("analyzer"), "-m", "diocle_analyzer", str(repo), "--out", str(out / "analysis-report.json"),
           "--samples-dir", str(out / "samples"), *(["--convert-anyway"] if convert_anyway else [])]
    subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300, cwd=REPO_ROOT / "services" / "analyzer")
    return json.loads((out / "analysis-report.json").read_text())


def run_pipeline(sample: Path, max_usd: float, convert_anyway: bool) -> tuple[str | None, int]:
    """Seam for tests. Runs `diocle_converter run` on the sample with a hard cap; returns (run folder name, exit code)."""
    cmd = [sys.executable, "-m", "diocle_converter", "run", str(sample), "--max-usd", f"{max_usd:.6f}", "--no-memory",
           *(["--convert-anyway"] if convert_anyway else [])]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if not convert_anyway:
        env.pop("DIOCLE_CONVERT_ANYWAY", None)
    proc = subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, errors="replace")
    run_name, deadline = None, time.monotonic() + RUN_TIMEOUT
    for line in proc.stdout:
        m = re.match(r"run started runs/(\S+)", line)
        if m:
            run_name = m.group(1)
        if line.strip():
            progress(line.strip())
        if time.monotonic() > deadline:
            proc.kill()
            progress("stopped: the run took longer than the time limit")
            break
    return run_name, proc.wait()


def _reason_from(run: dict) -> str:
    if run.get("assuranceReason"):
        return run["assuranceReason"]
    if run.get("error"):
        return run["error"]
    stages = [e.get("message") for e in run.get("events", []) if e.get("type") == "stage" and e.get("message")]
    return stages[-1] if stages else ""


def build_result(path: str, run: dict, run_copy: Path, sample: Path, max_usd: float) -> dict:
    """Point at the copied run. Everything that matters is copied from run.json, never recomputed."""
    label = run.get("assurance") or ("certified" if run.get("certified") else "failed")
    if label not in LABELS:
        label = "failed"
    if label == "certified" and not run.get("certified"):
        label = "failed"  # only a record that says certified: true may be shown as certified
    files: dict = {}
    java = sorted(str(p) for p in (run_copy / "java").glob("*.java")) if (run_copy / "java").is_dir() else []
    if java:
        files["java"] = java
    for key, name in (("sqlSchema", "schema.sql"), ("repairedCobol", None), ("diff", "cobol-repair.diff"), ("behaviorMd", "behavior.md")):
        p = run_copy / name if name else next(iter(sorted(run_copy.glob("*.repaired.cbl"))), None)
        if p and p.is_file():
            files[key] = str(p)
    repair = run.get("cobolRepair") or {}
    cost = (run.get("usage") or {}).get("estimatedCostUsd")
    result = {"version": VERSION, "command": "convert", "ok": True, "file": path, "assurance": label,
              "assuranceReason": _reason_from(run)[:1000], "runDir": str(run_copy), "files": files,
              "costUsd": cost, "maxUsd": max_usd, "model": run.get("model"), "notes": []}
    if repair.get("changedLines") is not None:
        result["repairedLines"] = int(repair["changedLines"])
    return result


def convert(path: str, copybooks: list[str], max_usd: float, convert_anyway: bool, runs_dir: Path) -> dict:
    source = Path(path)
    if not source.is_file():
        return _fail("convert", path, "file not found")
    if source.stat().st_size > MAX_SOURCE_BYTES:
        return _fail("convert", path, "file is larger than 2 MB")
    if not (0 < max_usd <= HARD_MAX_USD):
        return _fail("convert", path, f"--max-usd must be above 0 and at most {HARD_MAX_USD:.2f}")
    load_dotenv(Path.cwd() / ".env")  # a workspace .env fills what the environment lacks; the key is never printed
    try:
        Settings.from_env()
    except SystemExit as e:
        return _fail("convert", path, str(e) or "model settings are missing", maxUsd=max_usd)
    source = source.resolve()
    with tempfile.TemporaryDirectory(prefix="diocle-editor-") as tmp:
        tmp_dir = Path(tmp)
        n = stage_repo(source, copybooks, tmp_dir / "repo")
        progress(f"Analyzing {source.name} ({n} copybook files staged)")
        try:
            report = run_analyzer(tmp_dir / "repo", tmp_dir / "out", convert_anyway)
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            return _fail("convert", path, f"analysis failed: {type(e).__name__}", maxUsd=max_usd)
        programs = report.get("programs", [])
        if not programs:
            return _skipped(path, max_usd, "no program found in this file")
        program = programs[0]
        sample = tmp_dir / "out" / "samples" / program["name"].lower()
        if not (program.get("convertible") or convert_anyway) or not (sample / "sample.json").is_file():
            return _skipped(path, max_usd, program.get("notConvertibleReason") or "not convertible; enable convert-anyway to try")
        run_name, code = run_pipeline(sample, max_usd, convert_anyway)
        run_json = REPO_ROOT / "runs" / (run_name or "") / "run.json"
        if not run_name or not run_json.is_file():
            return _fail("convert", path, f"the converter stopped before a run was recorded (exit {code})", maxUsd=max_usd)
        run = json.loads(run_json.read_text())
        dest = runs_dir.resolve() / f"{source.stem}-{time.strftime('%Y%m%d-%H%M%S')}"
        shutil.copytree(REPO_ROOT / "runs" / run_name, dest)
        _extras(run, sample, dest)
    return build_result(path, run, dest, sample, max_usd)


def _skipped(path: str, max_usd: float, reason: str) -> dict:
    return {"version": VERSION, "command": "convert", "ok": True, "file": path, "assurance": "skipped",
            "assuranceReason": reason[:1000], "files": {}, "costUsd": 0.0, "maxUsd": max_usd, "model": None, "notes": []}


def _extras(run: dict, sample: Path, dest: Path) -> None:
    """Repair diff and patched COBOL from the record, and the SQL schema from the verifier's own module (best effort)."""
    repair = run.get("cobolRepair") or {}
    if repair.get("diff"):
        (dest / "cobol-repair.diff").write_text(repair["diff"])
    patched = next(iter(sorted(sample.rglob("*.repaired.cbl"))), None)
    if patched and repair:
        shutil.copy(patched, dest / patched.name)
    try:
        with tempfile.TemporaryDirectory(prefix="diocle-schema-") as tmp:
            subprocess.run([sys.executable, "-m", "diocle_verifier.sqlschema", str(sample), "--out", tmp], check=True,
                           capture_output=True, timeout=120)
            if (Path(tmp) / "schema.sql").is_file():
                shutil.copy(Path(tmp) / "schema.sql", dest / "schema.sql")
    except (subprocess.SubprocessError, OSError):
        pass


def main(argv: list[str]) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="diocle_converter editor")
    sub = p.add_subparsers(dest="what", required=True)
    for name in ("check", "convert"):
        s = sub.add_parser(name)
        s.add_argument("path")
        s.add_argument("--copybooks", action="append", default=[], metavar="DIR")
    c = sub.choices["convert"]
    c.add_argument("--max-usd", type=float, default=DEFAULT_MAX_USD)
    c.add_argument("--convert-anyway", action="store_true")
    c.add_argument("--runs-dir", type=Path, default=Path(".diocle") / "runs")
    a = p.parse_args(argv)
    result = check(a.path, a.copybooks) if a.what == "check" else convert(
        a.path, a.copybooks, a.max_usd, a.convert_anyway, a.runs_dir)
    print(json.dumps(result), flush=True)
    return 0
