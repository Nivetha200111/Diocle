"""Can GnuCOBOL build the ORIGINAL program? Answered before any model call (contracts/compile-check.schema.json).

Same compiler invocation as verification (runners.build_cobol: -x -std=ibm, IBM_FLAGS, the sample's copybook dir, its
CALLed modules, its collation), compile only, nothing is run. Imported COBOL is untrusted, so with DIOCLE_SANDBOX_URL
set (and not DIOCLE_IN_SANDBOX) the compile happens in the sandbox container and NEVER in this process, even when the
sandbox is busy or unreachable: then the answer is "unknown" and callers proceed as before.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .runners import build_cobol

VERSION = "0.1"
MAX_MESSAGE = 600
COMPILE_TIMEOUT = 30  # seconds for cobc; the sandbox job limit for a compile is longer (sandbox.COMPILE_JOB_TIMEOUT)

_PATH = re.compile(r"(?<![\w./-])(?:/[^\s:()'\"<>|]+)+")


@dataclass
class CompileCheck:
    status: str  # "ok" | "fail" | "unknown"
    message: str = ""

    def to_json(self) -> dict:
        return {"version": VERSION, "status": self.status, "message": self.message}


_DIAG = re.compile(r"^([^\s|>]+):(\d+): error: (.*)$")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_UNEXPECTED = re.compile(r"unexpected (\S+)")
_WORD = re.compile(r"^[A-Z][A-Z0-9-]{1,30}$")


def clean_message(text: str) -> str:
    """Only cobc's own diagnostics, `file:line: error: text`, and nothing else. cobc also echoes context lines of any
    file the source COPYs (even an absolute path), so such lines, 'warning' lines and every unrecognised line are
    dropped. Inside a kept line, quoted text is replaced by '...', an 'unexpected X' keeps X only when it looks
    like a COBOL word, absolute paths are reduced to file names, and the whole is bounded. Idempotent: the output
    (entries joined by ' | ') passes through again unchanged, which the client relies on."""
    kept = []
    for raw in re.split(r"\r?\n| \| ", text):
        m = _DIAG.match(_PATH.sub(lambda g: g.group(0).rstrip("/").rsplit("/", 1)[-1], raw.strip()))
        if not m:
            continue
        name, line, body = m.groups()
        body = _QUOTED.sub("'...'", body)
        body = _UNEXPECTED.sub(lambda u: u.group(0) if _WORD.match(u.group(1)) or u.group(1) == "'...'" else "unexpected ...", body)
        body = "".join(c for c in body if " " <= c <= "~")[:160]
        kept.append(f"{name.rsplit('/', 1)[-1][:60]}:{line}: error: {body}")
    return " | ".join(kept[:4])[:MAX_MESSAGE]


def compile_local(sample_dir: Path) -> CompileCheck:
    """Compile in this process. Only the sandbox job and developer machines (no sandbox configured) call this."""
    sample_dir = sample_dir.resolve()
    meta = json.loads((sample_dir / "sample.json").read_text())
    with tempfile.TemporaryDirectory(prefix="diocle-precheck-") as tmp:
        try:
            _, failed = build_cobol(sample_dir / meta["source"], sample_dir / meta["copybookDir"], Path(tmp),
                                    [sample_dir / m for m in meta.get("modules", [])], meta.get("collation", "ascii"),
                                    timeout=COMPILE_TIMEOUT)
        except subprocess.TimeoutExpired:
            return CompileCheck("unknown", f"compiling took longer than {COMPILE_TIMEOUT} seconds")
    if failed is None:
        return CompileCheck("ok")
    # "fail" only when cobc itself says why. A killed gcc, a full tmpfs, the pids limit or silence prove nothing.
    message = clean_message(failed.stderr + "\n" + failed.stdout) if (failed.exit_code or 0) > 0 else ""
    return CompileCheck("fail", message) if message else CompileCheck("unknown", "the compiler failed without a diagnostic")


def compile_original(sample_dir: Path, wait: float | None = None) -> CompileCheck:
    """wait: seconds to keep retrying while the sandbox is busy (default DIOCLE_SANDBOX_WAIT; callers pass less)."""
    if os.environ.get("DIOCLE_SANDBOX_URL") and not os.environ.get("DIOCLE_IN_SANDBOX"):
        from .sandbox import Busy, remote_compile

        try:
            return remote_compile(sample_dir.resolve(), wait)
        except Busy:
            return CompileCheck("unknown", "the sandbox was busy")
        except (OSError, ValueError, RuntimeError) as e:  # unreachable, refused, bad answer: never compile here instead
            return CompileCheck("unknown", f"the sandbox could not check: {str(e)[:200]}")
    try:
        return compile_local(sample_dir)
    except (OSError, ValueError, KeyError) as e:
        return CompileCheck("unknown", f"could not prepare the check: {str(e)[:200]}")


def main(argv: list[str] | None = None) -> int:
    """python -m diocle_verifier.precheck SAMPLE_DIR [--wait SECONDS]: prints the compile-check JSON (always exit 0)."""
    import argparse

    parser = argparse.ArgumentParser(prog="diocle_verifier.precheck")
    parser.add_argument("sample_dir", type=Path)
    parser.add_argument("--wait", type=float, default=None, help="seconds to retry while the sandbox is busy")
    args = parser.parse_args(argv)
    print(json.dumps(compile_original(args.sample_dir, args.wait).to_json()), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
