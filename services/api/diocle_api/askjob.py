"""The runner behind the ask button (started by asks.py; never by a request directly).

  python -m diocle_api.askjob JOB_ID AUDIO_PATH

JOB_ID is server-made and checked against asks.JOB_ID; the sample comes from the job record the server wrote (an enum value
mapped to a bundled directory), AUDIO_PATH is a bundled clip or the validated upload inside the job's own directory. The
converter's `ask` command is started with those and constants only. Claims run in the sandbox (DIOCLE_SANDBOX_URL).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from .asks import CLIPS_DIR, JOB_ID, MAX_USD, SAMPLE_DIRS, jobs_dir
from .runs import REPO_ROOT

SERVICES = REPO_ROOT / "services"
RUN_SECONDS = 4 * 60
ERR_NO_RESULT = "the ask stopped before it recorded a result"
_STAGE = re.compile(r"^stage (transcribing|claims|checking|answering): (.{0,300})$")
_STOPPED = re.compile(r"^stopped: ([A-Za-z0-9 .,()$\-]{3,160})$")  # our own fixed phrases (voice.VoiceError), never provider text


def converter_cmd(args: list[str]) -> list[str]:
    """Seam for tests: the converter's command line."""
    venv = SERVICES / "converter" / ".venv" / "bin" / "python"
    return [str(venv) if venv.exists() else sys.executable, "-m", "diocle_converter", *args]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Job:
    def __init__(self, job_id: str):
        self.path = jobs_dir() / job_id / "job.json"
        self.state = json.loads(self.path.read_text())

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2) + "\n")
        tmp.replace(self.path)

    def event(self, message: str, stage: str | None = None) -> None:
        self.state["events"] = (self.state["events"] + [{"at": now(), "message": message[:300]}])[-60:]
        if stage:
            self.state["stage"] = stage
        self.save()

    def finish(self, status: str, error: str | None = None) -> None:
        self.state.update(status=status, error=error, finishedAt=now(), stage="done" if status == "done" else "failed")
        self.save()


def _partial(job: Job, out: Path) -> None:
    try:
        data = json.loads((out / "ask-partial.json").read_text())
    except (OSError, ValueError):
        return
    keep = {}
    if isinstance(data.get("transcript"), dict):
        keep["transcript"] = data["transcript"]
    if isinstance(data.get("proposed"), list):
        keep["proposed"] = [str(s)[:400] for s in data["proposed"][:3]]
    job.state["partial"] = {**(job.state.get("partial") or {}), **keep}


def run(job: Job, audio: Path) -> None:
    sample, clip = job.state["sample"], job.state.get("clip")
    out = job.path.parent / "out"
    cmd = converter_cmd(["ask", str(SAMPLE_DIRS[sample]), "--audio", str(audio), "--max-usd", f"{MAX_USD:.6f}", "--out", str(out)])
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("DIOCLE_CONVERT_ANYWAY", None)
    job.event(f"Starting: hard cap ${MAX_USD:.2f} for the whole question", "transcribing")
    proc = subprocess.Popen(cmd, cwd=SERVICES / "converter", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                            errors="replace")
    timer = threading.Timer(RUN_SECONDS, proc.kill)
    timer.daemon = True
    timer.start()
    stopped = None
    try:
        for line in proc.stdout:
            line = line.strip()
            m = _STAGE.match(line)
            if m:
                _partial(job, out)
                job.event(m.group(2), m.group(1))
            elif _STOPPED.match(line):
                stopped = line[len("stopped: "):]
        proc.wait()
    finally:
        timer.cancel()
    try:
        result = json.loads((out / "ask.json").read_text())
    except (OSError, ValueError):
        job.finish("failed", stopped or ERR_NO_RESULT)
        return
    _partial(job, out)
    job.state["result"] = result
    job.event("Finished: the answer is assembled from claims GnuCOBOL confirmed", "done")
    job.finish("done")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or not JOB_ID.match(argv[0]):
        print("usage: python -m diocle_api.askjob JOB_ID AUDIO_PATH", file=sys.stderr)
        return 2
    job = Job(argv[0])
    audio = Path(argv[1]).resolve()
    allowed = audio.parent in (CLIPS_DIR.resolve(), job.path.parent.resolve()) and audio.suffix == ".wav" and job.state.get("sample") in SAMPLE_DIRS
    if not allowed:
        job.finish("failed", "the job stopped unexpectedly")
        return 2
    try:
        run(job, audio)
    except BaseException as e:  # never leave a job "running"; the record gets a fixed phrase, the log gets the type
        print(f"askjob failed: {type(e).__name__}", file=sys.stderr, flush=True)
        job.finish("failed", "the job stopped unexpectedly")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
