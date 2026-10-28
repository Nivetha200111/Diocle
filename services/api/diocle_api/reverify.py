"""Public re-verification of a certified run: original COBOL and the run's Java on fresh random inputs.

No model calls; CPU only. One at a time, so a visitor cannot queue up work on the server.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .runs import REPO_ROOT, RUN_ID, runs_dir

VERIFIER = REPO_ROOT / "services" / "verifier"
_lock = threading.Lock()


class Busy(RuntimeError):
    pass


def reverify_run(run_id: str, cases: int = 1000) -> dict | None:
    if not RUN_ID.match(run_id):
        return None
    run_path = runs_dir() / run_id
    meta_path = run_path / "run.json"
    if not meta_path.exists():
        return None
    run = json.loads(meta_path.read_text())
    sample = REPO_ROOT / run.get("sample", "")
    if not run.get("certified") or not run.get("sample") or not (sample / "sample.json").exists():
        raise ValueError("only certified runs with a recorded sample can be re-verified")
    if (run_path / "visitor").exists():
        raise ValueError("runs from visitor imports are not re-verified here")
    if not _lock.acquire(blocking=False):
        raise Busy("another re-verification is running; try again in a few seconds")
    try:
        seed = secrets.randbelow(10**9) + 10**6  # fresh, unpredictable, reported back
        started = time.time()
        with tempfile.TemporaryDirectory(prefix="diocle-reverify-") as tmp:
            out = Path(tmp) / "report.json"
            proc = subprocess.run([str(VERIFIER / ".venv/bin/python"), "-m", "diocle_verifier", str(sample),
                                   "--java-dir", str(run_path / "java"), "--seed", str(seed), "--random", str(cases),
                                   "--out", str(out)], cwd=VERIFIER, capture_output=True, text=True, timeout=1000,
                                  env={**os.environ, "DIOCLE_SANDBOX_WAIT": "20"})  # sandbox busy: say so, don't queue
            if not out.exists():
                if "engine is busy" in proc.stderr:
                    raise Busy("the verification engine is busy with a conversion; try again in a minute")
                raise RuntimeError("the verifier did not produce a report")
            report = json.loads(out.read_text())
        runs, s = report["runs"], report["summary"]
        failing = [r for r in report["results"] if not r["match"]]
        return {
            "runId": run_id, "seed": seed, "passed": s["passed"], "total": s["total"], "failed": s["failed"],
            "stdoutMatch": runs["stdoutMatch"], "exitCodeMatch": bool(runs.get("exitCodeMatch")),
            "allMatch": s["failed"] == 0 and s["total"] > 0 and runs["stdoutMatch"] and bool(runs.get("exitCodeMatch")),
            "firstMismatch": failing[0].get("diff") if failing else None,
            "seconds": round(time.time() - started, 1),
        }
    finally:
        _lock.release()
