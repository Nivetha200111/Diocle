"""Deliveries written by diocle_api.deliver (runs/deliveries/<id>/delivery.json), with live run and CI status."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from .runs import RUN_ID, get_run, runs_dir

_checks_cache: dict[str, tuple[float, list[dict]]] = {}


def _deliveries_dir():
    return runs_dir() / "deliveries"


def pr_checks(url: str) -> list[dict]:
    """CI checks on a pull request via the gh CLI, cached for 15 seconds; empty if gh is unavailable."""
    cached = _checks_cache.get(url)
    if cached and time.time() - cached[0] < 15:
        return cached[1]
    try:
        out = subprocess.run(["gh", "pr", "checks", url, "--json", "name,state,link"],
                             capture_output=True, text=True, timeout=20).stdout
        checks = json.loads(out) if out.strip() else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        checks = []
    _checks_cache[url] = (time.time(), checks)
    return checks


def _run_summary(run_id: str | None) -> dict | None:
    run = get_run(run_id) if run_id else None
    if not run:
        return None
    stages = [e for e in run["events"] if e["type"] == "stage"]
    return {
        "status": run["status"],
        "stage": stages[-1]["stage"] if stages else None,
        "events": run["events"][-8:],
        "steps": sum(1 for e in run["events"] if e["type"] == "agent-step"),
        "before": {k: run["before"][k] for k in ("passed", "total")} if run.get("before") else None,
        "after": {k: run["after"][k] for k in ("passed", "total")} if run.get("after") else None,
        "efficiency": run["efficiency"],
        "model": run["model"],
        "memoryUsed": (run.get("memory") or {}).get("used"),
    }


def list_deliveries() -> list[dict]:
    root = _deliveries_dir()
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob("*/delivery.json"), reverse=True):
        d = json.loads(path.read_text())
        out.append({k: d[k] for k in ("id", "legacy", "target", "stage", "startedAt", "finishedAt")}
                   | {"programs": len(d["programs"]), "pullRequest": (d.get("pullRequest") or {}).get("url")})
    return out


def get_delivery(delivery_id: str) -> dict | None:
    if not RUN_ID.match(delivery_id):
        return None
    path = _deliveries_dir() / delivery_id / "delivery.json"
    if not path.exists():
        return None
    d = json.loads(path.read_text())
    for p in d["programs"]:
        p["run"] = _run_summary(p.get("runId"))
    if d.get("pullRequest"):
        d["pullRequest"]["checks"] = pr_checks(d["pullRequest"]["url"])
    return d


# One start at a time across request threads: the busy check, the visitor budget and the new delivery record
# happen together, so parallel requests cannot start parallel jobs.
start_lock = threading.Lock()
_procs: dict[str, subprocess.Popen] = {}
MAX_HOURS = float(os.environ.get("DIOCLE_MAX_DELIVERY_HOURS", "6"))


def _alive(delivery_id: str, started_at: str) -> bool:
    """Is this delivery's process still running? A delivery started by an earlier api process (before a restart)
    or running past MAX_HOURS counts as dead, so one crash can never block every later start."""
    proc = _procs.get(delivery_id)
    age_h = (datetime.now(timezone.utc) - datetime.fromisoformat(started_at)).total_seconds() / 3600
    if proc is not None:
        running = proc.poll() is None
        pid = proc.pid
    else:  # started by an earlier api process, or from the command line: deliver.py records its pid
        pid_file = _deliveries_dir() / delivery_id / "pid"
        pid = int(pid_file.read_text()) if pid_file.exists() and pid_file.read_text().strip().isdigit() else None
        running = pid is not None and _is_deliver_process(pid)
        if pid is None and age_h < 2 / 60:
            return True  # just created; the process has not written its pid yet
    if running and age_h >= MAX_HOURS:
        try:
            os.killpg(pid, signal.SIGKILL)  # start_new_session: the whole delivery, converter included
        except (ProcessLookupError, PermissionError):
            pass
        return False
    return running


def _is_deliver_process(pid: int) -> bool:
    """True only for a live diocle_api.deliver process (a reused pid after a restart is something else)."""
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        cmdline = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return "diocle_api.deliver" in cmdline


def running_delivery() -> str | None:
    for item in list_deliveries():
        if item["stage"] in ("done", "failed"):
            continue
        if _alive(item["id"], item["startedAt"]):
            return item["id"]
        _mark_failed(item["id"], "interrupted: the engine restarted or the job was stopped")
    return None


def _mark_failed(delivery_id: str, error: str) -> None:
    path = _deliveries_dir() / delivery_id / "delivery.json"
    d = json.loads(path.read_text())
    if d["stage"] in ("done", "failed"):
        return
    d.update(stage="failed", error=d.get("error") or error, finishedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2) + "\n")
    tmp.replace(path)


def start_delivery(legacy: str, target: str | None, parallel: bool, breaker: bool, public: bool = False) -> str:
    """Start diocle_api.deliver in the background and return its id. One delivery at a time (rule 10).
    public: a visitor import (no target, any public repository, sandboxed, capped, no GitHub token)."""
    import sys

    from .deliver import GITHUB_URL, target_repo

    busy = running_delivery()
    if busy:
        raise RuntimeError(f"{busy} is still running")
    for url in (legacy, target) if target else (legacy,):
        if not GITHUB_URL.match(url.strip()):
            raise ValueError(f"not a GitHub repository URL: {url!r}")
    if target:
        target_repo(target)  # owner allowlist; the analyzer applies the same list to the legacy repo
    elif not public:
        raise ValueError("a target repository is required")
    delivery_id = f"delivery-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if (_deliveries_dir() / delivery_id).exists():
        raise RuntimeError("another delivery started this second; try again")
    cmd = [sys.executable, "-m", "diocle_api.deliver", legacy.strip(), *([target.strip()] if target else []),
           "--id", delivery_id, *(["--public"] if public else []),
           *(["--parallel"] if parallel else []), *(["--breaker"] if breaker else [])]
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if public:  # any owner may be imported; nothing in this process tree needs GitHub write access
        env["DIOCLE_IMPORT_ANY"] = "1"
        env.pop("GH_TOKEN", None)
    log = runs_dir() / "deliveries" / delivery_id / "deliver.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    # The record exists before this returns, so the next start sees a running delivery at once.
    record = {"id": delivery_id, "legacy": {"repository": legacy.strip(), "commit": None},
              "target": target.strip().rstrip("/").removesuffix(".git") if target else None, "public": public,
              "stage": "analyzing", "startedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "finishedAt": None, "error": None, "programs": [], "pullRequest": None}
    (log.parent / "delivery.json").write_text(json.dumps(record, indent=2) + "\n")
    proc = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parents[1], stdout=log.open("w"),
                            stderr=subprocess.STDOUT, env=env, start_new_session=True)
    if proc is not None:
        _procs[delivery_id] = proc
    return delivery_id
