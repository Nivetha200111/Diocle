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


def clean_message(text: str) -> str:
    """Compiler output for people: absolute paths reduced to file names, bounded in size and lines."""
    text = _PATH.sub(lambda m: m.group(0).rstrip("/").rsplit("/", 1)[-1], text.replace("\r", ""))
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    errors = [ln for ln in lines if "error" in ln.lower()] or lines
    return " | ".join(errors[:4])[:MAX_MESSAGE]


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
            return CompileCheck("fail", f"compiling took longer than {COMPILE_TIMEOUT} seconds")
    if failed is None:
        return CompileCheck("ok")
    return CompileCheck("fail", clean_message(failed.stderr + "\n" + failed.stdout) or "the compiler rejected the program")


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
