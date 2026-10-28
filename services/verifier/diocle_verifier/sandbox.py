"""Run untrusted builds and programs in a separate container that holds no secrets and has no internet.

Imported COBOL and model-written Java are code we did not write. On a public deployment the API container
holds the model key and the GitHub token, so every cobc, javac and program run is sent here instead
(runners._exec does that when DIOCLE_SANDBOX_URL is set).

  python -m diocle_verifier.sandbox            # serve on :8100 (inside the sandbox container)

The sandbox shares only the work directory (read-write) and the runs directory (read-only) with the API,
at the same paths, so commands and file paths need no translation.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

COMPILERS = {"cobc", "javac", "java"}
MAX_OUTPUT = 32 * 1024 * 1024  # bytes per stream; a program's whole stdout is compared, so keep it generous
MAX_TIMEOUT = 300


def _roots() -> list[Path]:
    return [Path(p).resolve() for p in os.environ.get("DIOCLE_SANDBOX_ROOTS", "").split(":") if p]


def _inside(path: str, roots: list[Path]) -> bool:
    p = Path(path).resolve()
    return any(p == r or r in p.parents for r in roots)


def check(job: dict, roots: list[Path]) -> str | None:
    """Why a job is refused, or None. Only the compilers, or a program built under a work root, may run."""
    cmd, cwd = job.get("cmd"), job.get("cwd")
    if not isinstance(cmd, list) or not cmd or not all(isinstance(c, str) for c in cmd):
        return "cmd must be a non-empty list of strings"
    if cmd[0] not in COMPILERS and not _inside(cmd[0], roots):
        return f"{cmd[0]!r} is not an allowed command"
    if cwd is not None and not _inside(cwd, roots):
        return "cwd must be inside a work root"
    if not isinstance(job.get("env", {}), dict):
        return "env must be an object"
    return None


def run(job: dict) -> dict:
    env = {str(k): str(v) for k, v in job.get("env", {}).items()}
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")  # the sandbox's own toolchain, never the caller's
    if os.environ.get("LD_LIBRARY_PATH"):
        env["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
    timeout = min(int(job.get("timeout", 120)), MAX_TIMEOUT)
    try:
        proc = subprocess.run(job["cmd"], env=env, cwd=job.get("cwd"), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"timeout": timeout}
    except OSError as e:
        return {"returncode": 127, "stdout": "", "stderr": str(e)}
    decode = lambda b: b[:MAX_OUTPUT].decode("utf-8", errors="replace")  # noqa: E731
    return {"returncode": proc.returncode, "stdout": decode(proc.stdout), "stderr": decode(proc.stderr)}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/exec":
            return self._send(404, {"error": "not found"})
        try:
            job = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "bad json"})
        refused = check(job, _roots())
        if refused:
            return self._send(403, {"error": refused})
        self._send(200, run(job))

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"sandbox {self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")


def main() -> int:
    if not _roots():
        sys.exit("DIOCLE_SANDBOX_ROOTS is not set")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("DIOCLE_SANDBOX_PORT", "8100"))), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
