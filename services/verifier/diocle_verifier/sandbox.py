"""Run whole verification jobs in a separate container that holds no secrets, has no internet and shares no files.

Imported COBOL and model-written Java are code we did not write. On a public deployment the API container holds
the model key and the GitHub token, so verify_sample() does not build or run anything there: it packs the sample
and the Java (regular files only) and posts them here (when DIOCLE_SANDBOX_URL is set). The sandbox unpacks them
into a private in-memory directory, runs the verifier, and answers with the report as JSON. Nothing a program
writes ever reaches the API's filesystem.

Inside the container the server runs as root with only SETUID, SETGID and KILL; each job runs as an unprivileged
user (JOB_UID), so a program can neither signal the server nor outlive its job: after every job the server
kills every process it can see, repeatedly, until none is left, and removes what the job wrote. The report
comes back on the job's stdout (a pipe), never from a file a program could replace.

  python -m diocle_verifier.sandbox            # serve on :8100 (inside the sandbox container)
"""

from __future__ import annotations

import base64
import io
import json
import os
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BUNDLE = 64 * 1024 * 1024  # bytes of sample + Java, packed
MAX_REPORT = 64 * 1024 * 1024
JOB_TIMEOUT = 300  # real jobs take seconds; a stuck or hostile job holds the sandbox at most this long
COMPILE_JOB_TIMEOUT = 60  # a compile-only check (POST /compile) is cheap, so it holds the sandbox far shorter
MAX_COMPILE_BUNDLE = 8 * 1024 * 1024  # a compile check takes the sample only (no Java)
MAX_COMPILE_REPORT = 16 * 1024
JOB_UID = 65534  # nobody
_job_lock = threading.Lock()


class Busy(RuntimeError):
    pass


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
    body = json.dumps(job).encode()
    # The sandbox runs one job at a time and answers 503 when busy; wait up to DIOCLE_SANDBOX_WAIT seconds.
    deadline = time.time() + float(os.environ.get("DIOCLE_SANDBOX_WAIT", "1800"))
    while True:
        req = urllib.request.Request(os.environ["DIOCLE_SANDBOX_URL"].rstrip("/") + "/verify", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=JOB_TIMEOUT + 60) as resp:
                return json.loads(resp.read(MAX_REPORT))
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:2000]
            if e.code != 503:
                raise RuntimeError(f"sandbox: {detail}") from e
            if time.time() > deadline:
                raise Busy("the verification engine is busy; try again in a minute") from e
            time.sleep(3)


def remote_compile(sample_dir: Path, wait: float | None = None):
    """Compile-only check of the original in the sandbox (contracts/compile-check.schema.json).
    Retries while the sandbox is busy for at most `wait` seconds (default DIOCLE_SANDBOX_WAIT), then raises Busy."""
    from .precheck import CompileCheck, clean_message

    packed = pack(sample_dir, None)
    if len(packed) > MAX_COMPILE_BUNDLE:
        raise ValueError("the sample is too large for a compile check")
    body = json.dumps({"bundle": base64.b64encode(packed).decode()}).encode()
    deadline = time.time() + (float(os.environ.get("DIOCLE_SANDBOX_WAIT", "1800")) if wait is None else wait)
    while True:
        req = urllib.request.Request(os.environ["DIOCLE_SANDBOX_URL"].rstrip("/") + "/compile", data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=COMPILE_JOB_TIMEOUT + 30) as resp:
                answer = json.loads(resp.read(MAX_COMPILE_REPORT))
            break
        except urllib.error.HTTPError as e:
            detail = e.read(2000).decode(errors="replace")
            if e.code != 503:
                raise RuntimeError(f"sandbox: {detail}") from e
            if time.time() >= deadline:
                raise Busy("busy") from e
            time.sleep(min(3, max(0.0, deadline - time.time())))
    if not isinstance(answer, dict) or answer.get("status") not in ("ok", "fail") or not isinstance(answer.get("message", ""), str):
        raise ValueError("the sandbox answered with something that is not a compile check")
    # Whatever came back is shown to people and to nobody else: paths reduced again, size bounded again.
    if answer["status"] == "ok":
        return CompileCheck("ok")
    message = clean_message(answer.get("message", ""))  # filtered again: only cobc diagnostics, whatever the sandbox sent
    if not message:
        raise ValueError("the sandbox reported a failure without a compiler diagnostic")
    return CompileCheck("fail", message)


# --- server side (the sandbox container) ---------------------------------------------------------------------

def _others() -> list[int]:
    me = os.getpid()
    return [int(e) for e in os.listdir("/proc") if e.isdigit() and int(e) not in (1, me)]


def _in_container() -> bool:
    return os.environ.get("DIOCLE_IN_SANDBOX") == "1" and os.path.isdir("/proc") and os.geteuid() == 0


def _kill_all() -> None:
    """Kill every process except this server and init, until none is left (a forking program cannot outrun it)."""
    for _ in range(200):
        if not _others():
            return
        try:
            os.kill(-1, signal.SIGKILL)  # Linux: every process we may signal, except init and ourselves
        except ProcessLookupError:
            pass
        time.sleep(0.05)


def _clean_up() -> None:
    """After a job: no process and no file of it is left. Only as root inside the sandbox container."""
    if not _in_container():
        return  # never on a developer machine
    _kill_all()
    # /tmp and /dev/shm are sticky, so the job's files are removed as the job's user.
    subprocess.run(["find", "/tmp", "/dev/shm", "-mindepth", "1", "-delete"], capture_output=True, timeout=60,
                   **_job_user())
    _kill_all()


def _job_user() -> dict:
    """Run jobs as an unprivileged user when the server is root (in the container); as-is elsewhere (tests)."""
    if os.geteuid() != 0:
        return {}
    return {"user": JOB_UID, "group": JOB_UID, "extra_groups": []}


def run_job(job: dict, kind: str = "verify") -> dict:
    """kind "verify": the whole verification; kind "compile": compile the original only (shorter limits)."""
    if kind not in ("verify", "compile"):
        raise ValueError("unknown job kind")
    if not _job_lock.acquire(blocking=False):
        raise Busy("busy")
    compile_only = kind == "compile"
    timeout = COMPILE_JOB_TIMEOUT if compile_only else JOB_TIMEOUT
    max_report = MAX_COMPILE_REPORT if compile_only else MAX_REPORT
    try:
        data = base64.b64decode(job["bundle"], validate=True)
        if len(data) > (MAX_COMPILE_BUNDLE if compile_only else MAX_BUNDLE):
            raise ValueError("bundle too large")
        params = {"kind": kind, "bundle": job["bundle"]} if compile_only else {
            "kind": kind, "seed": int(job.get("seed", 1026)), "randomCount": int(job.get("randomCount", 200)),
            "java": bool(job.get("java")), "extraCases": job.get("extraCases") or [], "bundle": job["bundle"]}
        proc = subprocess.Popen([sys.executable, "-m", "diocle_verifier.sandbox", "--job"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_job_env(),
                                start_new_session=True, cwd="/", **_job_user())
        timer = threading.Timer(timeout, lambda: _kill_all() if _in_container() else proc.kill())
        timer.start()
        try:
            proc.stdin.write(json.dumps(params).encode())
            proc.stdin.close()
            err = []
            threading.Thread(target=lambda: err.append(proc.stderr.read(64 * 1024)), daemon=True).start()
            out = proc.stdout.read(max_report + 1)
            proc.wait()
        finally:
            timer.cancel()
        if proc.returncode != 0 or len(out) > max_report:
            tail = (err[0] if err else b"").decode(errors="replace")[-1500:]
            raise RuntimeError(f"verifier failed (exit {proc.returncode}): {tail}")
        return json.loads(out)
    finally:
        _clean_up()
        _job_lock.release()


def _job_env() -> dict[str, str]:
    """The job runs the verifier locally: marked as inside the sandbox, never forwarding again."""
    keep = ("PATH", "LANG", "LC_ALL", "JAVA_HOME", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "PYTHONPATH")
    env = {k: v for k, v in os.environ.items() if k in keep}
    package_root = str(Path(__file__).resolve().parents[1])  # the job starts in "/", so name the package's home
    return {**env, "DIOCLE_IN_SANDBOX": "1", "HOME": "/tmp", "TMPDIR": tempfile.gettempdir(),
            "PYTHONUNBUFFERED": "1", "PYTHONPATH": package_root}


def _job_main() -> int:
    """Child: read the job on stdin, verify in a private directory, print the report on stdout."""
    from .inputs import Case
    from .verify import verify_sample

    params = json.loads(sys.stdin.buffer.read())
    with tempfile.TemporaryDirectory(prefix="job-") as tmp:
        work = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(params["bundle"], validate=True)), mode="r:gz") as tar:
            tar.extractall(work, filter="data")  # no absolute paths, no "..", no links out of work
        if params.get("kind") == "compile":
            from .precheck import compile_local

            sys.stdout.write(json.dumps(compile_local(work / "sample").to_json()))
            return 0
        cases = [Case(c["id"], c["source"], c["record"]) for c in params["extraCases"]]
        report = verify_sample(work / "sample", work / "java" if params["java"] else None, seed=params["seed"],
                               random_count=params["randomCount"], extra_cases=cases or None)
    sys.stdout.write(json.dumps(report))
    return 0


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/verify", "/compile"):
            return self._send(404, {"error": "not found"})
        kind = self.path[1:]
        length = int(self.headers.get("Content-Length", "0"))
        if length > (MAX_COMPILE_BUNDLE * 2 if kind == "compile" else MAX_BUNDLE * 2):
            return self._send(413, {"error": "job too large"})
        try:
            job = json.loads(self.rfile.read(length))
            self._send(200, run_job(job, kind))
        except Busy:
            self._send(503, {"error": "busy"})
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
        return _job_main()
    os.environ["DIOCLE_IN_SANDBOX"] = "1"  # the verifier runs here; never forward again
    os.environ.pop("DIOCLE_SANDBOX_URL", None)
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("DIOCLE_SANDBOX_PORT", "8100"))), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
