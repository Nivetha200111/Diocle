"""SQL schema for a run's record layouts, with its SQLite round-trip proof (contracts/sql-schema.schema.json).

Computed by the verifier (no model calls, no GnuCOBOL), once per sample: a sample's layouts do not change after its
runs, so a result is cached in memory. Failures (a timeout while a delivery holds the CPU, a broken sample) are not
cached, so the next request tries again; they are logged to stderr. One computation at a time.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from . import runs
from .reverify import VERIFIER

_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _python() -> str:
    venv = VERIFIER / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable  # cwd is the verifier, so its package imports either way


def _compute(sample: Path) -> dict | None:
    with tempfile.TemporaryDirectory(prefix="diocle-schema-") as tmp:
        try:
            proc = subprocess.run([_python(), "-m", "diocle_verifier.sqlschema", str(sample), "--out", tmp],
                                  cwd=VERIFIER, capture_output=True, text=True, timeout=120)
        except (subprocess.TimeoutExpired, OSError) as e:
            print(f"schema for {sample.name}: {type(e).__name__}: {e}", file=sys.stderr)
            return None
        out = Path(tmp) / "sql-schema.json"
        if not out.exists():
            print(f"schema for {sample.name}: no report (exit {proc.returncode}): {proc.stderr[-500:]}", file=sys.stderr)
            return None
        return json.loads(out.read_text())


def run_schema(run_id: str) -> dict | None:
    """The run's tables and round-trip proof, or None when there is nothing to show (unknown run, visitor run, no
    readable sample). Visitor runs are withheld like their sources: the layouts come from code Diocle does not control."""
    if not runs.RUN_ID.match(run_id):
        return None
    path = runs.runs_dir() / run_id
    try:
        run = json.loads((path / "run.json").read_text()) | {"_id": run_id}
    except (OSError, ValueError):
        return None
    if runs.is_visitor(path, run):
        return None
    sample = runs._sample_dir(run).resolve()
    if not any(sample.is_relative_to(r) for r in runs._sample_roots()) or not (sample / "sample.json").is_file():
        return None
    key = str(sample)
    with _lock:
        report = _cache.get(key) or _compute(sample)
        if report is not None:
            _cache[key] = report
    return None if report is None else {"runId": run_id, **report}
