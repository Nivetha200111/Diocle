"""The two public "try it live" buttons (contracts/live-sample.schema.json): policy, job records and the start path.

A visitor may start ONE of two fixed jobs, named from a fixed list, with no other input of any kind:

  addfee                   convert the bundled ADDFEE sample with Muse Spark and verify it (the normal run pipeline)
  loyalty-waiver-printout  read the bundled printout image with Muse Wonder and check the COBOL it wrote

On the two buttons, nothing a visitor sends reaches a model, a command line, a path or the sandbox: the request body is validated to a name from
SAMPLES, and the subprocess (samplejob.py) is started with that name's constants only. Caps (rule 10, set by the owner):
per run (--max-usd / VISION_MAX_USD), per visitor per day, per day overall, one job at a time across these buttons, visitor
imports and deliveries, and a daily dollar budget shared by both buttons that is itself drawn from the public daily budget.
Job records live in runs/live-samples/<id>/job.json; the 24-hour windows are read from them, so they survive a restart.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import shutil
import signal
import struct
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import public
from .runs import runs_dir

JOB_ID = re.compile(r"^live-[0-9]{8}-[0-9]{6}-[a-z]+$")
UPLOAD_BUCKET = "live:upload"
UPLOAD_MAX_USD, UPLOAD_PER_VISITOR, UPLOAD_PER_DAY = 0.10, 1, 3
MAX_IMAGE_BYTES, MAX_IMAGE_SIDE = 2 * 1024 * 1024, 1600
PRIVATE_SECONDS = 3600
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
    from .asks import spent as asks_spent  # the ask button draws on the same pool
    return convert_spent() + printout_spent() + asks_spent()


def _pid_is_samplejob(pid: int, module: str = "diocle_api.samplejob") -> bool:
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        cmdline = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout
    return module in cmdline


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
    from .asks import running_ask  # one job at a time across the live buttons and the ask button
    return running_ask()


def busy() -> str | None:
    from .deliveries import running_delivery

    return running_delivery() or running_job()


def cooldown_seconds() -> int:
    """Minimum gap between two live-sample starts, across all visitors (default 90 s). Stops one actor from holding the shared
    one-job-at-a-time lock back to back all day; the per-day counts and the budget are the hard limits."""
    try:
        return max(0, min(600, int(os.environ.get("DIOCLE_LIVE_COOLDOWN_SECONDS", "90"))))
    except ValueError:
        return 90


def cooldown_left() -> int:
    jobs = read_jobs()
    if not jobs:
        return 0
    newest = max(_stamp(j) for j in jobs)
    return max(0, int(cooldown_seconds() - (time.time() - newest) + 0.999))


def refusal(sample: str, visitor: str) -> Refused | None:
    """Why this sample may not start now, or None. The same function answers GET /config (the disabled reason on the button)
    and POST /samples/live, so the page can never offer what the engine would refuse."""
    cfg = SAMPLES[sample]
    if not switched_on():
        return Refused(403, "The live sample buttons are switched off on this server.")
    if public.visitor_left(f"live:{sample}", visitor, cfg["perVisitor"]) <= 0:
        return Refused(429, f"You have used your {cfg['perVisitor']} {cfg['label']} for today "
                            f"(limit per visitor per day: {cfg['perVisitor']}).")
    used = len([j for j in _last_day(read_jobs()) if j["sample"] == sample and not j.get("upload")])
    if used >= cfg["perDay"]:
        return Refused(429, f"All {cfg['perDay']} {cfg['label']} for today have been used "
                            f"(limit per day across all visitors: {cfg['perDay']}); the count resets after 24 hours.")
    return _shared_refusal(cfg["maxUsd"])


def _shared_refusal(max_usd: float) -> Refused | None:
    """The budget, one-at-a-time and cooldown rules every live job obeys."""
    total = spent()
    if total + max_usd > budget_usd():
        return Refused(429, f"The live page has used its ${budget_usd():.2f} model budget for the last 24 hours.")
    if public.spent_today() + max_usd > public.limits()["dailyBudgetUsd"]:
        return Refused(429, "The public daily model budget is used up for the last 24 hours; try again later.")
    other = busy()
    if other:
        return Refused(409, "Another conversion is running on this server right now. Try again when it finishes.")
    wait = cooldown_left()
    if wait > 0:
        return Refused(429, f"A live sample ran a moment ago; the buttons rest between runs so imports are not starved. "
                            f"Try again in {wait} seconds.")
    return None


def uploads_enabled() -> bool:
    """Visitors' own images and microphone clips. Kill switch: DIOCLE_PUBLIC_UPLOADS=0; the live buttons' switch also stops them."""
    return os.environ.get("DIOCLE_PUBLIC_UPLOADS", "1").strip().lower() not in ("0", "false", "off", "no") and switched_on()


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a strict walk of the segments up to the scan: fill bytes as decoders read them, exactly one frame
    header, and anything unexpected refused, so no decoder can see a larger picture than this does."""
    pos, size = 2, None
    while True:
        if pos >= len(data) or data[pos] != 0xFF:
            return None
        while pos < len(data) and data[pos] == 0xFF:
            pos += 1
        if pos + 2 >= len(data):
            return None
        marker = data[pos]
        pos += 1
        if marker == 0xDA:  # start of scan: the headers are over
            return size
        if marker in (0x00, 0x01, 0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            return None
        length = struct.unpack(">H", data[pos:pos + 2])[0]
        if length < 2 or pos + length > len(data):
            return None
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if size is not None or length < 7:
                return None
            height, width = struct.unpack(">HH", data[pos + 3:pos + 7])
            size = (width, height)
        pos += length


def image_problem(data: bytes) -> str | None:
    """Why these bytes are not an acceptable image, judged by the bytes alone: PNG or JPEG, small enough, and small enough in
    pixels that the pre-flight estimate of the model call (samplejob: 4,000 input tokens) holds. The page sends at most this."""
    if len(data) > MAX_IMAGE_BYTES:
        return f"the image is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB"
    size = None
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[8:16] == b"\x00\x00\x00\rIHDR" and len(data) >= 24:
        size = struct.unpack(">II", data[16:24])
    elif data[:2] == b"\xff\xd8":
        size = _jpeg_size(data)
    if size is None:
        return "the file is not a complete PNG or JPEG image"
    if not (0 < size[0] <= MAX_IMAGE_SIDE and 0 < size[1] <= MAX_IMAGE_SIDE):
        return f"the image must be at most {MAX_IMAGE_SIDE} pixels on each side"
    return None


def upload_refusal(visitor: str) -> Refused | None:
    """Why this visitor may not send an image now, or None. Runs before the body is read, and answers GET /config."""
    if not uploads_enabled():
        return Refused(403, "Reading your own image is switched off on this server.")
    if public.visitor_left(UPLOAD_BUCKET, visitor, UPLOAD_PER_VISITOR) <= 0:
        return Refused(429, f"You have used your {UPLOAD_PER_VISITOR} image read for today (limit per visitor per day: {UPLOAD_PER_VISITOR}).")
    if _uploads_today() >= UPLOAD_PER_DAY:
        return Refused(429, f"All {UPLOAD_PER_DAY} image reads for today have been used (limit per day across all visitors: "
                            f"{UPLOAD_PER_DAY}); the count resets after 24 hours.")
    return _shared_refusal(UPLOAD_MAX_USD)


def _uploads_today() -> int:
    return len([j for j in _last_day(read_jobs()) if j.get("public")])


def upload_status(visitor: str) -> dict:
    why = upload_refusal(visitor)
    return {"enabled": uploads_enabled(), "maxUsd": UPLOAD_MAX_USD, "perVisitorPerDay": UPLOAD_PER_VISITOR, "perDay": UPLOAD_PER_DAY,
            "usedToday": _uploads_today(), "visitorLeft": public.visitor_left(UPLOAD_BUCKET, visitor, UPLOAD_PER_VISITOR),
            "available": why is None, "reason": why.message if why else None, "maxBytes": MAX_IMAGE_BYTES}


def status(visitor: str) -> dict:
    """live-sample.schema.json $defs.status, for GET /config."""
    total = spent()
    buttons = {}
    for name, cfg in SAMPLES.items():
        why = refusal(name, visitor)
        buttons[cfg["kind"]] = {
            "maxUsd": cfg["maxUsd"], "perVisitorPerDay": cfg["perVisitor"], "perDay": cfg["perDay"],
            "usedToday": len([j for j in _last_day(read_jobs()) if j["sample"] == name and not j.get("upload")]),
            "visitorLeft": public.visitor_left(f"live:{name}", visitor, cfg["perVisitor"]),
            "available": why is None, "reason": why.message if why else None}
    return {"enabled": switched_on(), "budgetUsd": budget_usd(), "spentTodayUsd": total if total != float("inf") else None,
            "busy": busy() if switched_on() else None, "upload": upload_status(visitor), **buttons}


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
    return _launch(_new_job(job_id, sample, SAMPLES[sample]["maxUsd"]), kind)


def start_upload(data: bytes, visitor: str) -> tuple[str, str]:
    """Admit and start a read of the visitor's own image: the same printout path and sandbox as the bundled image. The caller
    holds deliveries.start_lock. Returns the job id and the key that alone can read its result."""
    why = upload_refusal(visitor)
    if why:
        raise why
    problem = image_problem(data)
    if problem:
        raise Refused(400, problem)
    job_id = f"live-{datetime.now().strftime('%Y%m%d-%H%M%S')}-printout"
    if (jobs_dir() / job_id).exists():
        raise Refused(409, "another job started this second; try again")
    try:
        public.visitor_hit(UPLOAD_BUCKET, visitor, UPLOAD_PER_VISITOR)
    except PermissionError as e:
        raise Refused(429, str(e)) from e
    job = _new_job(job_id, "loyalty-waiver-printout", UPLOAD_MAX_USD)
    key = secrets.token_urlsafe(24)
    job.update(upload=True, public=True, viewKey=key, uploadImage="upload.png" if data[:1] == b"\x89" else "upload.jpg")
    path = jobs_dir() / job_id / job["uploadImage"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return _launch(job, "printout"), key


def _new_job(job_id: str, sample: str, max_usd: float) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {"version": "0.1", "id": job_id, "sample": sample, "status": "running", "stage": "starting", "startedAt": now,
            "finishedAt": None, "error": None, "maxUsd": max_usd, "events": [], "runId": None, "printout": None}


def may_read(job: dict, key: str | None) -> bool:
    """A public upload's result belongs to whoever sent it. Other jobs are open to anyone."""
    stored = job.get("viewKey")
    return not stored or (isinstance(key, str) and hmac.compare_digest(stored.encode(), key.encode("utf-8", "surrogateescape")))


def private_is_old(job: dict) -> bool:
    """A finished upload keeps its result for PRIVATE_SECONDS, long enough for the visitor to read it."""
    finished = job.get("finishedAt")
    if job.get("status") == "running" or not job.get("public") or job.get("wiped") or not finished:
        return False
    try:
        return datetime.now(timezone.utc) - datetime.fromisoformat(finished) > timedelta(seconds=PRIVATE_SECONDS)
    except ValueError:
        return True


def wipe_private(job: dict) -> dict:
    """What remains of a visitor's job after an hour: an allow-list, with the cost in the shape the budgets read."""
    kept = {k: job[k] for k in ("version", "id", "sample", "clip", "status", "stage", "startedAt", "finishedAt", "maxUsd", "upload", "public",
                                "pid") if k in job}
    kept.update(events=[], error=None, runId=None, wiped=True, partial=None)
    usage = (job.get("printout") or {}).get("usage")
    kept["printout"] = {"usage": usage} if usage else None
    costs = (job.get("result") or {}).get("costs")
    kept["result"] = {"costs": costs} if costs else None
    return kept


def sweep_private() -> None:
    """For every public upload that is not running: delete everything but its record, whatever ended it (a crash, a kill, an
    engine restart), and past the hour reduce the record to wipe_private. Runs at engine start, then on a timer."""
    from .asks import jobs_dir as asks_dir
    running_job()  # marks the jobs whose process died
    for root in (jobs_dir(), asks_dir()):
        for path in root.glob("*/job.json"):
            try:
                job = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(job, dict) or not job.get("public") or job.get("status") == "running":
                continue
            for child in path.parent.iterdir():
                if child.name != "job.json":
                    shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
            if private_is_old(job):
                tmp = path.with_suffix(".tmp")
                tmp.write_text(json.dumps(wipe_private(job), indent=2) + "\n")
                tmp.replace(path)


def _launch(job: dict, kind: str) -> str:
    job_id = job["id"]
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


def get_job(job_id: str, key: str | None = None) -> dict | None:
    """live-sample.schema.json $defs.job (the process id and anything else internal are left out). An upload's result is
    shown only with its key, and is removed from disk an hour after the job ends; the spend record stays."""
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
    if private_is_old(job):
        job = wipe_private(job)
        _write(job)
    view = {k: job.get(k) for k in _VIEW}
    if job.get("wiped") or not may_read(job, key):
        view.update(events=[], printout=None, runId=None)
    return view
