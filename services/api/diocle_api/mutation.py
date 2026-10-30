"""Mutation testing of a certified run's Java (contracts/mutation-report.schema.json): how strong is the verification?

Like re-verification: CPU only, no model calls, one job at a time (the same lock, so it also never overlaps a
re-verification), certified runs with a recorded sample only, never visitor runs. The Java runs in the sandbox
container whenever DIOCLE_SANDBOX_URL is set (the verifier CLI forwards the job). The report is written to the run's
directory as mutation-report.json and served from there. A short pause between jobs stops a visitor from keeping the
engine busy with back-to-back requests.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from .reverify import REPO_ROOT, RUN_ID, VERIFIER, Busy, _lock, is_visitor, runs_dir

COOLDOWN_SECONDS = 60
_last_finished = 0.0


def get_mutation(run_id: str) -> dict | None:
    """The stored report, or None (unknown run, no report yet, unreadable file)."""
    if not RUN_ID.match(run_id):
        return None
    try:
        report = json.loads((runs_dir() / run_id / "mutation-report.json").read_text())
    except (OSError, ValueError):
        return None
    return report if isinstance(report, dict) and report.get("version") == "0.1" else None


def run_mutation(run_id: str) -> dict | None:
    global _last_finished
    if not RUN_ID.match(run_id):
        return None
    run_path = runs_dir() / run_id
    meta_path = run_path / "run.json"
    if not meta_path.exists():
        return None
    run = json.loads(meta_path.read_text())
    sample = REPO_ROOT / run.get("sample", "")
    if not run.get("certified") or not run.get("sample") or not (sample / "sample.json").exists():
        raise ValueError("only certified runs with a recorded sample can be mutation tested")
    if is_visitor(run_path, run | {"_id": run_id}):
        raise ValueError("runs from visitor imports are not mutation tested here")
    if not _lock.acquire(blocking=False):
        raise Busy("another verification job is running; try again in a few seconds")
    try:
        wait = COOLDOWN_SECONDS - (time.time() - _last_finished)
        if wait > 0:
            raise Busy(f"a mutation run finished a moment ago; try again in {int(wait) + 1} seconds")
        python = VERIFIER / ".venv/bin/python"
        proc = subprocess.run([str(python) if python.exists() else "python3", "-m", "diocle_verifier", "mutate", str(run_path)],
                              cwd=VERIFIER, capture_output=True, text=True, timeout=1000,
                              env={**os.environ, "DIOCLE_SANDBOX_WAIT": "20"})  # sandbox busy: say so, don't queue
        _last_finished = time.time()
        report = get_mutation(run_id)
        if report is None or report.get("runId") != run_id:
            if "engine is busy" in proc.stderr:
                raise Busy("the verification engine is busy with a conversion; try again in a minute")
            raise RuntimeError("the verifier did not produce a mutation report")
        return report
    finally:
        _lock.release()
