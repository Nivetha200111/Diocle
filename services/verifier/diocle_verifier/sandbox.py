"""Run whole verification jobs in a separate container that holds no secrets, has no internet and shares no files.

Imported COBOL and model-written Java are code we did not write. On a public deployment the API container holds
the model key and the GitHub token, so verify_sample() does not build or run anything there: it packs the sample
and the Java (regular files only) and posts them here (when DIOCLE_SANDBOX_URL is set). The sandbox unpacks them
into a private in-memory directory, runs the verifier, and answers with the report as JSON. Nothing a program
writes ever reaches the API's filesystem, and after every job every other process in the container is killed,
so nothing a program starts survives into the next job.

  python -m diocle_verifier.sandbox            # serve on :8100 (inside the sandbox container)
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BUNDLE = 64 * 1024 * 1024  # bytes of sample + Java, packed
MAX_REPORT = 64 * 1024 * 1024
JOB_TIMEOUT = 900
_job_lock = threading.Lock()


# --- client side (the API container) -------------------------------------------------------------------------

def pack(sample_dir: Path, java_dir: Path | None) -> bytes:
    """tar.gz of sample/ and java/: regular files only, symlinks and special files skipped, size-capped."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for prefix, root in (("sample", sample_dir), ("java", java_dir)):
            if root is None:
                continue
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                for name in filenames:
                    path = Path(dirpath) / name
                    if not stat.S_ISREG(os.lstat(path).st_mode):
                        continue
                    tar.add(path, arcname=f"{prefix}/{path.relative_to(root).as_posix()}", recursive=False)
            if buf.tell() > MAX_BUNDLE:
                raise ValueError("sample and Java are too large to verify")
    return buf.getvalue()


def remote_verify(sample_dir: Path, java_dir: Path | None, seed: int, random_count: int,
                  extra_cases: list | None) -> dict:
    job = {"bundle": base64.b64encode(pack(sample_dir, java_dir)).decode(), "java": java_dir is not None,
           "seed": seed, "randomCount": random_count,
           "extraCases": [{"id": c.id, "source": c.source, "record": c.record} for c in extra_cases or []]}
    req = urllib.request.Request(os.environ["DIOCLE_SANDBOX_URL"].rstrip("/") + "/verify",
                                 data=json.dumps(job).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=JOB_TIMEOUT + 60) as resp:
            return json.loads(resp.read(MAX_REPORT))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"sandbox: {e.read().decode(errors='replace')[:500]}") from e


# --- server side (the sandbox container) ---------------------------------------------------------------------

def _kill_others() -> None:
    """SIGKILL every process except this server and the container's init (compose `init: true`)."""
    if os.environ.get("DIOCLE_IN_SANDBOX") != "1" or not os.path.isdir("/proc"):
        return  # only inside the sandbox container; never on a developer machine
    me = os.getpid()
    for entry in os.listdir("/proc"):
        if entry.isdigit() and int(entry) not in (1, me):
            try:
                os.kill(int(entry), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


def run_job(job: dict) -> dict:
    with _job_lock:
        work = Path(tempfile.mkdtemp(prefix="job-"))
        try:
            data = base64.b64decode(job["bundle"], validate=True)
            if len(data) > MAX_BUNDLE:
                raise ValueError("bundle too large")
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
                tar.extractall(work, filter="data")  # no absolute paths, no "..", no links out of work
            params = {"seed": int(job.get("seed", 1026)), "randomCount": int(job.get("randomCount", 200)),
                      "java": bool(job.get("java")), "extraCases": job.get("extraCases") or []}
            (work / "job.json").write_text(json.dumps(params))
            proc = subprocess.run([sys.executable, "-m", "diocle_verifier.sandbox", "--job", str(work)],
                                  capture_output=True, text=True, timeout=JOB_TIMEOUT, start_new_session=True,
                                  env=_job_env())
            report = work / "report.json"
            fd = os.open(report, os.O_RDONLY | os.O_NOFOLLOW) if report.exists() else None
            if fd is None or proc.returncode != 0:
                raise RuntimeError(f"verifier failed: {(proc.stderr or proc.stdout)[-800:]}")
            with os.fdopen(fd, "rb") as f:
                return json.loads(f.read(MAX_REPORT))
        finally:
            _kill_others()
            shutil.rmtree(work, ignore_errors=True)


def _job_env() -> dict[str, str]:
    """The job runs the verifier locally: marked as inside the sandbox, never forwarding again."""
    env = {k: v for k, v in os.environ.items() if k != "DIOCLE_SANDBOX_URL"}
    return {**env, "DIOCLE_IN_SANDBOX": "1"}


def _job_main(work: Path) -> int:
    from .inputs import Case
    from .verify import verify_sample

    params = json.loads((work / "job.json").read_text())
    cases = [Case(c["id"], c["source"], c["record"]) for c in params["extraCases"]]
    report = verify_sample(work / "sample", work / "java" if params["java"] else None, seed=params["seed"],
                           random_count=params["randomCount"], extra_cases=cases or None)
    (work / "report.json").write_text(json.dumps(report))
    return 0


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/verify":
            return self._send(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", "0"))
        if length > MAX_BUNDLE * 2:
            return self._send(413, {"error": "job too large"})
        try:
            job = json.loads(self.rfile.read(length))
            self._send(200, run_job(job))
        except subprocess.TimeoutExpired:
            self._send(504, {"error": f"verification took longer than {JOB_TIMEOUT}s"})
        except (ValueError, KeyError, TypeError, tarfile.TarError, RuntimeError) as e:
            self._send(400, {"error": str(e)[:800]})

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"sandbox {self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--job"]:
        return _job_main(Path(argv[1]))
    os.environ["DIOCLE_IN_SANDBOX"] = "1"  # the verifier runs here; never forward again
    os.environ.pop("DIOCLE_SANDBOX_URL", None)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("DIOCLE_SANDBOX_PORT", "8100"))), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
