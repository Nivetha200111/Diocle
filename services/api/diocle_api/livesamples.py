"""The two public "try it live" buttons (contracts/live-sample.schema.json): policy, job records and the start path.

A visitor may start ONE of two fixed jobs, named from a fixed list, with no other input of any kind:

  addfee                   convert the bundled ADDFEE sample with Muse Spark and verify it (the normal run pipeline)
  loyalty-waiver-printout  read the bundled printout image with Muse Wonder and check the COBOL it wrote

Nothing a visitor sends reaches a model, a command line, a path or the sandbox: the request body is validated to a name from
SAMPLES, and the subprocess (samplejob.py) is started with that name's constants only. Caps (rule 10, set by the owner):
per run (--max-usd / VISION_MAX_USD), per visitor per day, per day overall, one job at a time across these buttons, visitor
imports and deliveries, and a daily dollar budget shared by both buttons that is itself drawn from the public daily budget.
Job records live in runs/live-samples/<id>/job.json; the 24-hour windows are read from them, so they survive a restart.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import public
from .runs import runs_dir

JOB_ID = re.compile(r"^live-[0-9]{8}-[0-9]{6}-[a-z]+$")
MAX_JOB_SECONDS = 30 * 60

# The only things a start can mean. `kind` names the runner in samplejob.py; the numbers are hard caps (they can be lowered
# by the owner's code change, never by a request).
SAMPLES = {
    "addfee": {"kind": "convert", "maxUsd": 0.02, "perVisitor": 3, "perDay": 20, "label": "conversions"},
    "loyalty-waiver-printout": {"kind": "printout", "maxUsd": 0.10, "perVisitor": 1, "perDay": 5, "label": "printout reads"},
}
BY_KIND = {v["kind"]: k for k, v in SAMPLES.items()}

_procs: dict[str, subprocess.Popen] = {}


class Refused(Exception):
    """A start that may not happen now. `status` is the HTTP status the API answers with; `message` is for the visitor."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def jobs_dir() -> Path:
    return runs_dir() / "live-samples"


def switched_on() -> bool:
    """Kill switch: DIOCLE_PUBLIC_SAMPLES=0 turns both buttons off. Unset, they follow DIOCLE_PUBLIC_IMPORTS=1. They always
    need the sandbox (the originals and model-written code never run beside the secrets)."""
    flag = os.environ.get("DIOCLE_PUBLIC_SAMPLES")
    on = flag == "1" or (flag is None and os.environ.get("DIOCLE_PUBLIC_IMPORTS") == "1")
    return on and bool(os.environ.get("DIOCLE_SANDBOX_URL"))


def budget_usd() -> float:
    """What both buttons together may spend in 24 hours: DIOCLE_PUBLIC_SAMPLES_BUDGET (default 1.0), never more than the daily budget."""
    try:
        value = float(os.environ.get("DIOCLE_PUBLIC_SAMPLES_BUDGET", "") or "1.0")
    except ValueError:
        value = 1.0
    return max(0.0, min(value, public.limits()["dailyBudgetUsd"]))


def _stamp(job: dict) -> float:
    try:
        return datetime.fromisoformat(job["startedAt"]).timestamp()
    except (KeyError, ValueError, TypeError):
        return 0.0


def read_jobs() -> list[dict]:
    jobs = []
    for path in jobs_dir().glob("*/job.json"):
        try:
            job = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(job, dict) and JOB_ID.match(str(job.get("id", ""))) and job.get("sample") in SAMPLES:
            jobs.append(job)
    return jobs


def _last_day(jobs: list[dict]) -> list[dict]:
    cutoff = time.time() - 86400
    return [j for j in jobs if _stamp(j) >= cutoff]


def _run_cost(run_id: str | None) -> float | None:
    """The estimated cost of the run a convert job started (None: unknown price with calls made; 0.0 before a run exists)."""
    if not run_id or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_id):
        return 0.0
    try:
        usage = json.loads((runs_dir() / run_id / "run.json").read_text()).get("usage", {})
    except (OSError, ValueError):
        return 0.0
    cost = usage.get("estimatedCostUsd")
    return None if cost is None and usage.get("calls") else float(cost or 0)


def printout_spent() -> float:
    """Estimated spend of printout jobs in the last 24 hours. A job still running, or one that ended without a result, counts
    at its full cap (the worst case); an unknown price makes the total infinite: the budget fails closed."""
    total = 0.0
    for job in _last_day(read_jobs()):
        if SAMPLES[job["sample"]]["kind"] != "printout":
            continue
        result = job.get("printout")
        if isinstance(result, dict):
            cost = (result.get("usage") or {}).get("estimatedCostUsd")
            if cost is None:
                return float("inf")
            total += float(cost)
        else:
            total += SAMPLES[job["sample"]]["maxUsd"]
    return round(total, 4)


def convert_spent() -> float:
    total = 0.0
    for job in _last_day(read_jobs()):
        if SAMPLES[job["sample"]]["kind"] == "convert":
            cost = _run_cost(job.get("runId"))
            if cost is None:
                return float("inf")
            total += cost
    return round(total, 4)


def spent() -> float:
    return convert_spent() + printout_spent()


def _pid_is_samplejob(pid: int) -> bool:
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        cmdline = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return "diocle_api.samplejob" in cmdline


def _alive(job: dict) -> bool:
    age = time.time() - _stamp(job)
    proc = _procs.get(job["id"])
    pid = job.get("pid")
    if proc is not None:
        running, pid = proc.poll() is None, proc.pid
    elif isinstance(pid, int):
        running = _pid_is_samplejob(pid)
    else:
        return age < 120  # just created; the process has not recorded its pid yet
    if running and age >= MAX_JOB_SECONDS:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, TypeError):
            pass
        return False
    return running


def _write(job: dict) -> None:
    path = jobs_dir() / job["id"] / "job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=2) + "\n")
    tmp.replace(path)


def running_job() -> str | None:
    """Id of a live sample job that is still running. One whose process died (an engine restart) is marked failed."""
    for job in read_jobs():
        if job.get("status") != "running":
            continue
        if _alive(job):
            return job["id"]
        job.update(status="failed", error=job.get("error") or "interrupted: the engine restarted or the job was stopped",
                   finishedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _write(job)
    return None


def busy() -> str | None:
    from .deliveries import running_delivery

    return running_delivery() or running_job()


def refusal(sample: str, visitor: str) -> Refused | None:
    """Why this sample may not start now, or None. The same function answers GET /config (the disabled reason on the button)
    and POST /samples/live, so the page can never offer what the engine would refuse."""
    cfg = SAMPLES[sample]
    if not switched_on():
        return Refused(403, "The live sample buttons are switched off on this server.")
    if public.visitor_left(f"live:{sample}", visitor, cfg["perVisitor"]) <= 0:
        return Refused(429, f"You have used your {cfg['perVisitor']} {cfg['label']} for today "
                            f"(limit per visitor per day: {cfg['perVisitor']}).")
    used = len([j for j in _last_day(read_jobs()) if j["sample"] == sample])
    if used >= cfg["perDay"]:
        return Refused(429, f"All {cfg['perDay']} {cfg['label']} for today have been used "
                            f"(limit per day across all visitors: {cfg['perDay']}); the count resets after 24 hours.")
    total = spent()
    if total + cfg["maxUsd"] > budget_usd():
        return Refused(429, f"The two live buttons have used their ${budget_usd():.2f} model budget for the last 24 hours.")
    if public.spent_today() + cfg["maxUsd"] > public.limits()["dailyBudgetUsd"]:
        return Refused(429, "The public daily model budget is used up for the last 24 hours; try again later.")
    other = busy()
    if other:
        return Refused(409, "Another conversion is running on this server right now. Try again when it finishes.")
    return None


def status(visitor: str) -> dict:
    """live-sample.schema.json $defs.status, for GET /config."""
    total = spent()
    buttons = {}
    for name, cfg in SAMPLES.items():
        why = refusal(name, visitor)
        buttons[cfg["kind"]] = {
            "maxUsd": cfg["maxUsd"], "perVisitorPerDay": cfg["perVisitor"], "perDay": cfg["perDay"],
            "usedToday": len([j for j in _last_day(read_jobs()) if j["sample"] == name]),
            "visitorLeft": public.visitor_left(f"live:{name}", visitor, cfg["perVisitor"]),
            "available": why is None, "reason": why.message if why else None}
    return {"enabled": switched_on(), "budgetUsd": budget_usd(), "spentTodayUsd": total if total != float("inf") else None,
            "busy": busy() if switched_on() else None, **buttons}


def start(sample: str, visitor: str) -> str:
    """Admit and start a job. The caller holds deliveries.start_lock. `sample` must already be a key of SAMPLES."""
    if sample not in SAMPLES:
        raise Refused(400, "unknown sample")
    why = refusal(sample, visitor)
    if why:
        raise why
    kind = SAMPLES[sample]["kind"]
    job_id = f"live-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{kind}"
    if (jobs_dir() / job_id).exists():
        raise Refused(409, "another job started this second; try again")
    try:
        public.visitor_hit(f"live:{sample}", visitor, SAMPLES[sample]["perVisitor"])
    except PermissionError as e:
        raise Refused(429, str(e)) from e
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    job = {"version": "0.1", "id": job_id, "sample": sample, "status": "running", "stage": "starting", "startedAt": now,
           "finishedAt": None, "error": None, "maxUsd": SAMPLES[sample]["maxUsd"], "events": [], "runId": None,
           "printout": None}
    _write(job)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    for name in ("GH_TOKEN", "DIOCLE_CONVERT_ANYWAY", "DIOCLE_ADMIN_TOKEN"):
        env.pop(name, None)
    log = jobs_dir() / job_id / "job.log"
    # argv: this interpreter, the module, a server-made id and a constant kind. Nothing from the request.
    proc = subprocess.Popen([sys.executable, "-m", "diocle_api.samplejob", job_id, kind], cwd=Path(__file__).resolve().parents[1],
                            stdout=log.open("w"), stderr=subprocess.STDOUT, env=env, start_new_session=True)
    _procs[job_id] = proc
    job["pid"] = proc.pid
    _write(job)
    return job_id


_VIEW = ("version", "id", "sample", "status", "stage", "startedAt", "finishedAt", "error", "maxUsd", "events", "runId", "printout")


def get_job(job_id: str) -> dict | None:
    """live-sample.schema.json $defs.job (the process id and anything else internal are left out)."""
    if not JOB_ID.match(job_id):
        return None
    try:
        job = json.loads((jobs_dir() / job_id / "job.json").read_text())
    except (OSError, ValueError):
        return None
    if job.get("status") == "running" and not _alive(job):
        running_job()  # marks the dead job failed
        try:
            job = json.loads((jobs_dir() / job_id / "job.json").read_text())
        except (OSError, ValueError):
            return None
    return {k: job.get(k) for k in _VIEW}
