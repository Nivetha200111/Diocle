"""The runner behind the two live sample buttons (started by livesamples.start; never by a request directly).

  python -m diocle_api.samplejob JOB_ID convert|printout

JOB_ID is made by the server and checked against livesamples.JOB_ID; the kind is one of two words. Everything else that
reaches a command line below is a constant in this file: the bundled sample directories, the bundled image and the dollar
caps. No visitor value is read here at all. Model-written code is built and run only by the sandbox (the printout goes
through `transcribe --sandbox`, which refuses to run without it).
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

from .livesamples import JOB_ID, SAMPLES, jobs_dir
from .runs import REPO_ROOT, runs_dir

SERVICES = REPO_ROOT / "services"
ADDFEE = REPO_ROOT / "samples" / "addfee"
PRINTOUT_IMAGE = REPO_ROOT / "samples" / "loyalty-waiver-printout" / "listing.png"
PRINTOUT_ORIGINAL = REPO_ROOT / "samples" / "loyalty-waiver"
RUN_SECONDS = 15 * 60  # a conversion of this program takes about a minute; this only stops a stuck one
MAX_SOURCE_BYTES = 30000

# Fixed phrases: the only error strings that reach a job record.
ERR_NO_RUN = "the converter stopped before it recorded a run"
ERR_RUN_CUT = "the run did not finish (stopped or timed out)"
ERR_NO_RESULT = "the printout intake stopped before it recorded a result"

# Progress lines of `transcribe` that the page may show (written by our own code, never model text).
_PRINTOUT_LINES = re.compile(r"^(vision model: [\w.\-/]+|call \d+: [\d ,/a-z().=\-$]+|attempt \d+: compile (?:OK|FAILED)"
                             r"|the transcription is built and run by the injected checker.*)$")


def python_for(service: str) -> str:
    venv = SERVICES / service / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def converter_cmd(args: list[str]) -> list[str]:
    """Seam for tests: the converter's command line."""
    return [python_for("converter"), "-m", "diocle_converter", *args]


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

    def finish(self, status: str, error: str | None = None, stage: str | None = None) -> None:
        self.state.update(status=status, error=error, finishedAt=now(), **({"stage": stage} if stage else {}))
        self.save()


def _watch(proc: subprocess.Popen, seconds: int) -> threading.Timer:
    timer = threading.Timer(seconds, proc.kill)
    timer.daemon = True
    timer.start()
    return timer


def run_convert(job: Job) -> None:
    cap = SAMPLES["addfee"]["maxUsd"]
    cmd = converter_cmd(["run", str(ADDFEE), "--max-usd", f"{cap:.6f}", "--no-memory"])
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("DIOCLE_CONVERT_ANYWAY", None)
    job.event(f"Starting the converter on the bundled ADDFEE sample (hard cap ${cap:.2f})", "starting")
    proc = subprocess.Popen(cmd, cwd=SERVICES / "converter", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, errors="replace")
    timer = _watch(proc, RUN_SECONDS)
    run_id = None
    try:
        for line in proc.stdout:
            m = re.match(r"run started runs/([A-Za-z0-9][A-Za-z0-9._-]*)$", line.strip())
            if m and run_id is None:
                run_id = m.group(1)
                # The marker makes the run a labelled "live sample run" (run schema v0.16 sampleRun).
                (runs_dir() / run_id).mkdir(parents=True, exist_ok=True)
                (runs_dir() / run_id / "sample-run.json").write_text(json.dumps({"sample": "addfee", "job": job.state["id"]}) + "\n")
                job.state["runId"] = run_id
                job.event(f"Run {run_id} started: the page now follows its own events", "running")
        proc.wait()
    finally:
        timer.cancel()
    if run_id is None:
        job.finish("failed", ERR_NO_RUN, "failed")
        return
    try:
        run = json.loads((runs_dir() / run_id / "run.json").read_text())
    except (OSError, ValueError):
        run = {}
    status = run.get("status")
    if status in ("certified", "not-certified") or run.get("certified") is True:
        verdict = "certified" if run.get("certified") else "not certified"
        job.event(f"Finished: {verdict}", "done")
        job.finish("done", None, "done")
    else:
        job.finish("failed", ERR_RUN_CUT, "failed")


def reduce_transcription(rec: dict, source: str | None) -> dict:
    """live-sample.schema.json $defs.printout from the converter's transcription.json (contracts/transcription.schema.json)."""
    usage = rec.get("usage") or {}
    d = rec.get("differential")
    attempts = [{"n": a.get("n", i + 1), "compileOk": bool((a.get("compile") or {}).get("ok")),
                 **({"errors": str((a.get("compile") or {}).get("errors", ""))[:1500]} if not (a.get("compile") or {}).get("ok") else {})}
                for i, a in enumerate(rec.get("attempts") or [])][:5]
    diff = None
    if isinstance(d, dict):
        diff = {"ran": bool(d.get("ran")), "inputs": int(d.get("inputs", 0)), "matched": int(d.get("matched", 0)),
                "mismatched": int(d.get("mismatched", 0))}
        for key in ("stdoutMatch", "exitCodeMatch"):
            if isinstance(d.get(key), bool):
                diff[key] = d[key]
        if d.get("reason"):
            diff["reason"] = str(d["reason"])[:400]
        if d.get("ranIn") == "sandbox":
            diff["ranIn"] = "sandbox"
    cost = usage.get("estimatedCostUsd")
    return {"status": rec.get("status"), "reason": (str(rec["reason"])[:600] if rec.get("reason") else None),
            "model": rec.get("model"), "program": rec.get("program"), "source": source,
            "usage": {"calls": int(usage.get("calls", 0)), "inputTokens": int(usage.get("inputTokens", 0)),
                      "outputTokens": int(usage.get("outputTokens", 0)),
                      "estimatedCostUsd": None if cost is None else float(cost)},
            "attempts": attempts, "differential": diff}


def run_printout(job: Job) -> None:
    cap = SAMPLES["loyalty-waiver-printout"]["maxUsd"]
    out = job.path.parent / "out"
    cmd = converter_cmd(["transcribe", str(PRINTOUT_IMAGE), "--out", str(out), "--against", str(PRINTOUT_ORIGINAL), "--sandbox"])
    # The bundled image is about 1.5k input tokens (measured). The pre-flight worst case is 4000 input + 4000 output tokens
    # at Muse Wonder's list prices = $0.096 <= the $0.10 cap; max_tokens stays a hard bound on what a call can bill.
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "VISION_MAX_USD": f"{cap:.6f}", "VISION_MAX_OUTPUT_TOKENS": "4000",
           "VISION_INPUT_TOKENS_ESTIMATE": "4000"}
    job.event(f"Sending the bundled printout image to the vision model (hard cap ${cap:.2f})", "reading")
    proc = subprocess.Popen(cmd, cwd=SERVICES / "converter", text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, errors="replace")
    timer = _watch(proc, RUN_SECONDS)
    try:
        for line in proc.stdout:
            line = line.strip()
            if _PRINTOUT_LINES.match(line):
                job.event(line[:300].replace("the transcription is built and run by the injected checker (the sandbox container), "
                                             "not on this machine", "Compiling and running the transcription in the sandbox"),
                          "checking" if line.startswith(("attempt", "the transcription")) else None)
        proc.wait()
    finally:
        timer.cancel()
    try:
        rec = json.loads((out / "transcription.json").read_text())
    except (OSError, ValueError):
        job.finish("failed", ERR_NO_RESULT, "failed")
        return
    source = None
    if rec.get("source") and isinstance(rec["source"], str):
        path = (out / rec["source"]).resolve()
        if path.is_relative_to(out.resolve()) and path.is_file():
            source = path.read_bytes()[:MAX_SOURCE_BYTES].decode("utf-8", errors="replace")
    job.state["printout"] = reduce_transcription(rec, source)
    job.event(f"Finished: {rec.get('status')}", "done")
    job.finish("done", None, "done")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or not JOB_ID.match(argv[0]) or argv[1] not in ("convert", "printout") or not argv[0].endswith("-" + argv[1]):
        print("usage: python -m diocle_api.samplejob JOB_ID convert|printout", file=sys.stderr)
        return 2
    job = Job(argv[0])
    try:
        (run_convert if argv[1] == "convert" else run_printout)(job)
    except BaseException as e:  # never leave a job "running"; the record gets a fixed phrase, the log gets the type
        print(f"samplejob failed: {type(e).__name__}", file=sys.stderr, flush=True)
        job.finish("failed", "the job stopped unexpectedly", "failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
