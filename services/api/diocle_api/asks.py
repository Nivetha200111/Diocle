"""The public "Ask the original program" button (contracts/voice-question.schema.json): policy, job records and the start path.

PUBLIC path: a visitor names one bundled sample and one bundled clip from fixed lists. There is no upload surface: nothing a
visitor sends reaches a model, a path, a command line or the sandbox except those two enum values. The bundled clips are
synthetic-voice WAV files in voice_clips/. LOCAL/ADMIN path (start_upload): one uploaded WAV, validated by its bytes (16 kHz
mono 16-bit PCM, at most 10 s and 500 KB) before anything is written; gated in app.py like createTarget and convert-anyway.

Caps (rule 10, set by the owner's code, never by a request): $0.01 per ask, 5 asks per visitor per day, 30 per day overall,
one job at a time across asks, the live buttons, imports and deliveries, and the spend counts against the same
DIOCLE_PUBLIC_SAMPLES_BUDGET pool as the two live buttons (itself drawn from the public daily budget). Kill switch:
DIOCLE_PUBLIC_SAMPLES=0 (also off when voice transcription is not configured). Job records: runs/asks/<id>/job.json.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import livesamples, public
from .livesamples import Refused
from .runs import REPO_ROOT, runs_dir

JOB_ID = re.compile(r"^ask-[0-9]{8}-[0-9]{6}-[a-z0-9]{4}$")
MAX_JOB_SECONDS = 5 * 60
CLIPS_DIR = Path(__file__).resolve().parent / "voice_clips"
MAX_USD, PER_VISITOR, PER_DAY = 0.01, 5, 30
BUCKET = "ask"

# (sample, spoken question): the only things a public start can mean.
CLIPS = {
    "fee-overdrawn": {"sample": "interest-accrual", "question": "What happens to the fee when the account is overdrawn?"},
    "waiver-tenure": {"sample": "loyalty-waiver", "question": "Is the fee waived for an account with a ten-year tenure?"},
}
SAMPLES = ("interest-accrual", "loyalty-waiver")
SAMPLE_DIRS = {name: REPO_ROOT / "samples" / name for name in SAMPLES}

_procs: dict[str, subprocess.Popen] = {}


def _voice():
    """services/converter's voice module (stdlib only), for the byte checks and the voice settings."""
    path = str(REPO_ROOT / "services" / "converter")
    if path not in sys.path:
        sys.path.append(path)
    from diocle_converter import voice
    return voice


def jobs_dir() -> Path:
    return runs_dir() / "asks"


def voice_configured() -> bool:
    return _voice().VoiceSettings.from_env() is not None


def switched_on() -> bool:
    """Kill switch for the PUBLIC path: DIOCLE_PUBLIC_SAMPLES=0 turns it off. Needs the sandbox and a voice configuration."""
    return livesamples.switched_on() and voice_configured()


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
        if isinstance(job, dict) and JOB_ID.match(str(job.get("id", ""))):
            jobs.append(job)
    return jobs


def _last_day(jobs: list[dict]) -> list[dict]:
    cutoff = time.time() - 86400
    return [j for j in jobs if _stamp(j) >= cutoff]


def spent() -> float:
    """Estimated spend of asks in the last 24 hours. A job still running, or one that ended without a result, counts at its
    full cap (the worst case); an unknown price makes the total infinite: the budget fails closed."""
    total = 0.0
    for job in _last_day(read_jobs()):
        result = job.get("result")
        if isinstance(result, dict):
            cost = (result.get("costs") or {}).get("totalUsd")
            if cost is None:
                return float("inf")
            total += float(cost)
        else:
            total += MAX_USD
    return round(total, 4)


def _alive(job: dict) -> bool:
    age = time.time() - _stamp(job)
    proc = _procs.get(job["id"])
    pid = job.get("pid")
    if proc is not None:
        running, pid = proc.poll() is None, proc.pid
    elif isinstance(pid, int):
        running = livesamples._pid_is_samplejob(pid, "diocle_api.askjob")
    else:
        return age < 120
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


def running_ask() -> str | None:
    """Id of an ask that is still running. One whose process died (an engine restart) is marked failed."""
    for job in read_jobs():
        if job.get("status") != "running":
            continue
        if _alive(job):
            return job["id"]
        job.update(status="failed", stage="failed", error=job.get("error") or "interrupted: the engine restarted or the job was stopped",
                   finishedAt=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        _write(job)
    return None


def cooldown_seconds() -> int:
    try:
        return max(0, min(600, int(os.environ.get("DIOCLE_ASK_COOLDOWN_SECONDS", "10"))))
    except ValueError:
        return 10


def cooldown_left() -> int:
    jobs = read_jobs()
    if not jobs:
        return 0
    return max(0, int(cooldown_seconds() - (time.time() - max(_stamp(j) for j in jobs)) + 0.999))


def refusal(visitor: str) -> Refused | None:
    """Why a PUBLIC ask may not start now, or None. Answers GET /config (the disabled reason on the button) and POST /asks."""
    if not livesamples.switched_on():
        return Refused(403, "The live buttons are switched off on this server.")
    if not voice_configured():
        return Refused(403, "Voice transcription is not configured on this server.")
    if public.visitor_left(BUCKET, visitor, PER_VISITOR) <= 0:
        return Refused(429, f"You have used your {PER_VISITOR} questions for today (limit per visitor per day: {PER_VISITOR}).")
    used = len(_last_day(read_jobs()))
    if used >= PER_DAY:
        return Refused(429, f"All {PER_DAY} questions for today have been used (limit per day across all visitors: {PER_DAY}); "
                            "the count resets after 24 hours.")
    return _shared_refusal()


def _shared_refusal() -> Refused | None:
    if livesamples.spent() + MAX_USD > livesamples.budget_usd():
        return Refused(429, f"The live buttons have used their ${livesamples.budget_usd():.2f} model budget for the last 24 hours.")
    if public.spent_today() + MAX_USD > public.limits()["dailyBudgetUsd"]:
        return Refused(429, "The public daily model budget is used up for the last 24 hours; try again later.")
    if livesamples.busy():
        return Refused(409, "Another conversion is running on this server right now. Try again when it finishes.")
    wait = cooldown_left()
    if wait > 0:
        return Refused(429, f"A question ran a moment ago. Try again in {wait} seconds.")
    return None


def status(visitor: str, may_upload: bool) -> dict:
    """voice-question $defs.status, for GET /config."""
    why = refusal(visitor)
    return {"enabled": switched_on(), "available": why is None, "reason": why.message if why else None, "maxUsd": MAX_USD,
            "perVisitorPerDay": PER_VISITOR, "perDay": PER_DAY, "usedToday": len(_last_day(read_jobs())),
            "visitorLeft": public.visitor_left(BUCKET, visitor, PER_VISITOR), "uploadsAllowed": bool(may_upload) and voice_configured(),
            "clips": [{"clip": name, "sample": c["sample"], "question": c["question"],
                       "seconds": round(max(0, (CLIPS_DIR / f"{name}.wav").stat().st_size - 44) / 32000, 1)} for name, c in CLIPS.items()]}


def _new_job(sample: str, clip: str | None, audio: Path) -> dict:
    now = datetime.now(timezone.utc)
    job_id = f"ask-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"
    job = {"version": "0.1", "id": job_id, "sample": sample, "clip": clip, "status": "running", "stage": "starting",
           "startedAt": now.isoformat(timespec="seconds"), "finishedAt": None, "error": None, "events": [], "result": None,
           "partial": None}
    return job


def _launch(job: dict, audio: Path) -> str:
    _write(job)
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    for name in ("GH_TOKEN", "DIOCLE_CONVERT_ANYWAY", "DIOCLE_ADMIN_TOKEN"):
        env.pop(name, None)
    log = jobs_dir() / job["id"] / "job.log"
    # argv: this interpreter, the module and a server-made id. The sample and the audio path are read from the job record the
    # server wrote (an enum value and a path under the job directory or the bundled clips), never from the request.
    proc = subprocess.Popen([sys.executable, "-m", "diocle_api.askjob", job["id"], str(audio)],
                            cwd=Path(__file__).resolve().parents[1], stdout=log.open("w"), stderr=subprocess.STDOUT, env=env,
                            start_new_session=True)
    _procs[job["id"]] = proc
    job["pid"] = proc.pid
    _write(job)
    return job["id"]


def start(sample: str, clip: str, visitor: str) -> str:
    """Admit and start a PUBLIC ask. The caller holds deliveries.start_lock. `sample` and `clip` must be enum values."""
    if sample not in SAMPLES or clip not in CLIPS or CLIPS[clip]["sample"] != sample:
        raise Refused(400, "unknown sample or clip")
    why = refusal(visitor)
    if why:
        raise why
    try:
        public.visitor_hit(BUCKET, visitor, PER_VISITOR)
    except PermissionError as e:
        raise Refused(429, str(e)) from e
    return _launch(_new_job(sample, clip, CLIPS_DIR / f"{clip}.wav"), CLIPS_DIR / f"{clip}.wav")


def start_upload(sample: str, wav: bytes) -> str:
    """Admit and start an ask on an UPLOADED clip (local or admin path only: app.py gates the caller). Validated by bytes first.
    Not counted against the per-visitor or per-day public limits, but it keeps the dollar cap, the budget pool and the
    one-job-at-a-time rule."""
    if sample not in SAMPLES:
        raise Refused(400, "unknown sample")
    voice = _voice()
    try:
        voice.validate_wav(wav)
    except voice.VoiceError as e:
        raise Refused(400, str(e)) from None
    if not voice_configured():
        raise Refused(403, "Voice transcription is not configured on this server.")
    why = _shared_refusal()
    if why:
        raise why
    job = _new_job(sample, None, Path())
    job["upload"] = True
    path = jobs_dir() / job["id"] / "upload.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav)
    return _launch(job, path)


_VIEW = ("version", "id", "sample", "clip", "status", "stage", "startedAt", "finishedAt", "error", "events", "result", "partial")


def get_job(job_id: str) -> dict | None:
    """voice-question $defs.job (the process id and anything else internal are left out)."""
    if not JOB_ID.match(job_id):
        return None
    try:
        job = json.loads((jobs_dir() / job_id / "job.json").read_text())
    except (OSError, ValueError):
        return None
    if job.get("status") == "running" and not _alive(job):
        running_ask()
        try:
            job = json.loads((jobs_dir() / job_id / "job.json").read_text())
        except (OSError, ValueError):
            return None
    return {k: job.get(k) for k in _VIEW}
