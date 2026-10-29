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
from dataclasses import dataclass, field
from pathlib import Path

from .runners import build_cobol

VERSION = "0.2"
MAX_DIAGNOSTICS = 4
MAX_DIAGNOSTIC = 200
COMPILE_TIMEOUT = 30  # seconds for cobc; the sandbox job limit for a compile is longer (sandbox.COMPILE_JOB_TIMEOUT)

# Fixed phrases for "unknown": nothing a program, a COPYed file or the sandbox says ever becomes part of them.
NOTE_BUSY = "the sandbox was busy"
NOTE_SANDBOX = "the sandbox could not check this program"
NOTE_SANDBOX_ERROR = "the sandbox returned an error"
NOTE_NO_DIAGNOSTIC = "the compiler failed without a diagnostic"
NOTE_TIMEOUT = f"compiling took longer than {COMPILE_TIMEOUT} seconds"
NOTE_PREPARE = "could not prepare the check"

_PATH = re.compile(r"(?<![\w./-])(?:/[^\s:()'\"<>|]+)+")
_DIAG = re.compile(r"^([\w.$-]+):(\d+): error: (.*)$")  # cobc's own form; gcc's `foo.c:12:5: error:` does not match
_CONTEXT = re.compile(r"^\s*(\d+\s*)?[|>]")  # cobc echoes source lines as `    2 |  <line>` or `>`: never diagnostics
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9-]*|\d+|.", re.S)
_FILE_TROUBLE = re.compile(r"No such file|Permission denied|Is a directory|Not a directory|cannot open|Too many open", re.I)
_PUNCT = set(",.:;()' -/")


@dataclass
class CompileCheck:
    """status "fail" carries `diagnostics` (a list, never a joined string); "unknown" carries a fixed `note`."""

    status: str  # "ok" | "fail" | "unknown"
    note: str = ""
    diagnostics: list[str] = field(default_factory=list)

    @property
    def message(self) -> str:
        """For people: the diagnostics for a failure, else the note."""
        return " | ".join(self.diagnostics) if self.diagnostics else self.note

    def to_json(self) -> dict:
        return {"version": VERSION, "status": self.status, "note": self.note, "diagnostics": list(self.diagnostics)}


def _mask(body: str) -> str:
    """Words of cobc's own messages pass; anything else (a name, a literal, a file's content) becomes '...'."""
    from .diag_words import WORDS

    if _FILE_TROUBLE.search(body):
        return "cannot read a COPY file"  # one reason: absent, unreadable and forbidden paths are not told apart
    out = []
    for tok in _TOKEN.findall(_QUOTED.sub("'...'", body)):
        if tok[0].isalpha():
            out.append(tok if tok.lower() in WORDS or tok in ("A", "B") else "...")
        elif tok.isdigit() or tok in _PUNCT:
            out.append(tok)
        # any other character (control, non-ASCII, symbols) is dropped
    return re.sub(r"(\.\.\.\s*){2,}", "... ", "".join(out)).strip()[:160]


def clean_diagnostic(raw: str) -> str | None:
    """One line of compiler output -> a safe `file:line: error: text`, or None when it is not cobc's own diagnostic.
    Idempotent, so the client can apply it again to what the sandbox sent."""
    if len(raw) > 2000 or _CONTEXT.match(raw):
        return None
    m = _DIAG.match(_PATH.sub(lambda g: g.group(0).rstrip("/").rsplit("/", 1)[-1], raw))
    if not m:
        return None
    name, line, body = m.groups()
    return f"{name[:60]}:{line[:6]}: error: {_mask(body)}"[:MAX_DIAGNOSTIC]


def diagnostics(text: str) -> list[str]:
    """cobc's `file:line: error: ...` lines only. The text is split on line ends and nothing else: cobc echoes source
    context (`    2 |        <line of a file the program COPYs>`), which is dropped before any matching, and no
    separator that file content could contain is ever used to cut it into 'lines'."""
    found = (clean_diagnostic(raw) for raw in re.split(r"\r\n|\n|\r", text))
    return [d for d in found if d][:MAX_DIAGNOSTICS]


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
            return CompileCheck("unknown", NOTE_TIMEOUT)
    if failed is None:
        return CompileCheck("ok")
    # "fail" only when cobc itself says why. A killed gcc, a full tmpfs, the pids limit or silence prove nothing.
    found = diagnostics(failed.stderr + "\n" + failed.stdout) if (failed.exit_code or 0) > 0 else []
    return CompileCheck("fail", diagnostics=found) if found else CompileCheck("unknown", NOTE_NO_DIAGNOSTIC)


def compile_original(sample_dir: Path, wait: float | None = None) -> CompileCheck:
    """wait: seconds to keep retrying while the sandbox is busy (default DIOCLE_SANDBOX_WAIT; callers pass less)."""
    if os.environ.get("DIOCLE_SANDBOX_URL") and not os.environ.get("DIOCLE_IN_SANDBOX"):
        from .sandbox import Busy, SandboxError, remote_compile

        try:
            return remote_compile(sample_dir.resolve(), wait)
        except Busy:
            return CompileCheck("unknown", NOTE_BUSY)
        except SandboxError:  # the sandbox refused or failed: its body is never shown
            return CompileCheck("unknown", NOTE_SANDBOX_ERROR)
        except (OSError, ValueError, RuntimeError):  # unreachable, bad answer: never compile here instead
            return CompileCheck("unknown", NOTE_SANDBOX)
    try:
        return compile_local(sample_dir)
    except (OSError, ValueError, KeyError):
        return CompileCheck("unknown", NOTE_PREPARE)


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
