"""Build and run the original COBOL (GnuCOBOL) and the converted Java with the same DD-style file bindings."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn


@dataclass
class Run:
    compiled: bool | None  # None: not attempted (the converted program tampered, see not_run); False: it does not compile
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    output_lines: list[str] = field(default_factory=list)
    output_files: dict[str, list[str]] = field(default_factory=dict)  # DD name -> records (multi-file runs)


class VerifierUnavailable(RuntimeError):
    """The verifier itself lacks something it needs (not a verdict on the program). The message is for a person."""

    plain_message = True


class ProgramTimeout(subprocess.TimeoutExpired):
    """A program under test ran past the time limit. A TimeoutExpired (callers that tolerate one, such as mutation
    testing, still do), but its message is the sentence a person should read, never the raw command line."""

    plain_message = True

    def __init__(self, side: str, cmd, timeout: float):
        super().__init__(cmd, timeout)
        self.side = side

    def __str__(self) -> str:
        n = int(self.timeout) if float(self.timeout).is_integer() else self.timeout
        if self.side == "original":
            return f"the original program did not terminate within {n} seconds, so there is nothing to compare against"
        return f"the converted Java did not terminate within {n} seconds, so it cannot be certified"


def side_of(label: str) -> str:
    return "original" if label.startswith("original") else "converted"


def _exec_side(side: str, cmd: list[str], **kw):
    """_exec for running (not building) one side: a timeout becomes a ProgramTimeout that names the side."""
    try:
        return _exec(cmd, **kw)
    except subprocess.TimeoutExpired as e:
        raise ProgramTimeout(side, cmd, e.timeout) from None


# Only what compilers and the programs need. Code we run (model-written Java, imported COBOL) must never
# inherit secrets such as model API keys that the converter loads into its own environment.
_ENV_ALLOW = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "JAVA_HOME", "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
_ENV_PREFIXES = ("COB_",)


def safe_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k in _ENV_ALLOW or k.startswith(_ENV_PREFIXES)}
    return {**env, **(extra or {})}


def _exec(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None, timeout: int = 120):
    # stdin is closed: a program that ACCEPTs from the console sees end of file on both sides, never the caller's terminal.
    # Bytes decoded 1:1 as latin-1: stdout is the whole result of a DISPLAY-only program, so non-UTF-8 bytes must not
    # raise and a lone CR must not be turned into LF (text mode would do both).
    proc = subprocess.run(cmd, env=safe_env(env), cwd=cwd, capture_output=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)
    proc.stdout, proc.stderr = proc.stdout.decode("latin-1"), proc.stderr.decode("latin-1")
    return proc


# IBM Enterprise COBOL defaults that GnuCOBOL's -std=ibm leaves off: TRUNC(STD) (binary values are truncated to
# their PIC digits) and DISPLAY of binary items showing their PIC digits, not the full binary width.
IBM_FLAGS = ["-fbinary-truncate", "-fpretty-display"]

_FREE_DIRECTIVE = re.compile(r"^\s*(?:>>\s*SOURCE\s+(?:FORMAT\s+)?(?:IS\s+)?FREE|\$\s*SET\s+SOURCEFORMAT\s*\(?[\"']?FREE)", re.I)


def format_flags(source: Path) -> list[str]:
    """["-free"] when the source opens with >>SOURCE FORMAT FREE (or $SET SOURCEFORMAT"FREE"): -std=ibm reads fixed
    format, where a directive in column 1 is sequence-area text and code past column 72 is cut off."""
    try:
        with source.open(errors="replace") as f:
            first = next((line for line in f if line.strip()), "")
    except OSError:
        return []
    return ["-free"] if _FREE_DIRECTIVE.match(first) else []


_ASSIGN_WORD = re.compile(r"\bASSIGN\s+(?:TO\s+)?([A-Z0-9][A-Z0-9-]*-[A-Z0-9-]*[A-Z0-9])\b", re.I)


def assign_flags(source: Path) -> list[str]:
    """Full-name file assignment for ASSIGN TO INPUT-FILE. Under -std=ibm GnuCOBOL reads a hyphenated ASSIGN name
    as label-name (INPUT-FILE opens DD "FILE", so INPUT-FILE and OUTPUT-FILE collide), while the analyzer, the JCL
    and the Java all use the whole name as the DD name (DD_INPUT-FILE). With a hyphenated, unquoted ASSIGN name the
    program is compiled to look the whole name up, so both sides open the same files; names without a hyphen keep
    the IBM rule."""
    try:
        text = source.read_text(errors="replace")
    except OSError:
        return []
    return ["-fassign-clause=dynamic", "-fimplicit-assign-dynamic-var"] if _ASSIGN_WORD.search(text) else []


def build_executable(exe: Path, main: Path, others: list[Path], flags: list[str], workdir: Path,
                     timeout: int = 120, libs: list[str] | None = None) -> subprocess.CompletedProcess:
    """cobc -x the entry program with its CALLed modules and stand-ins. One command when every file needs the same
    per-file flags (source format, ASSIGN naming), as before; otherwise each file is compiled to an object with its
    own flags and then linked, because -free on the command line would apply to a fixed-format module too.
    libs: linker arguments (-lsqlite3 for the EXEC SQL shim), given to whichever command links."""
    libs = libs or []
    files = [main, *others]
    formats = [format_flags(f) + assign_flags(f) for f in files]
    if all(f == formats[0] for f in formats):
        return _exec(["cobc", "-x", "-std=ibm", *flags, *formats[0], "-o", str(exe), *map(str, files), *libs], timeout=timeout)
    objects = workdir / "objects"
    objects.mkdir(exist_ok=True)
    built = []
    for i, (path, fmt) in enumerate(zip(files, formats)):
        obj = objects / f"{i:02d}-{path.stem}.o"
        step = _exec(["cobc", "-c", "-std=ibm", *(["-x"] if i == 0 else []), *flags, *fmt, "-o", str(obj), str(path)],
                     timeout=timeout)
        if step.returncode != 0:
            return step
        built.append(str(obj))
    return _exec(["cobc", "-x", "-std=ibm", "-o", str(exe), *built, *libs], timeout=timeout)


# Both sides see the same "now": GnuCOBOL through COB_CURRENT_DATE, Java through DIOCLE_CLOCK (ISO-8601, UTC).
CLOCK = "2000-02-29T13:45:10.00Z"
CLOCK_ENV = {"COB_CURRENT_DATE": "2000/02/29 13:45:10.00", "DIOCLE_CLOCK": CLOCK, "TZ": "UTC"}


def read_records(path: Path, fmt: str = "line", length: int = 0) -> list[str]:
    """Output records as latin-1 strings: text lines, or fixed-length byte records with no separators."""
    if not path.exists():
        return []
    data = path.read_bytes().decode("latin-1")
    if fmt == "fixed":
        return [data[i : i + length] for i in range(0, len(data), length)] if length else []
    return data.splitlines()


class OutputLines(list):
    """A text file's lines, and whether its last line ended in a newline byte. That fact is beside the lines, not among
    them: nothing a program prints can stand in for it."""

    final_newline: bool = True


def read_output(path: Path, fmt: str = "line", length: int = 0) -> list[str]:
    """An output file's records for comparison. Text lines end at a newline byte and nothing else: a form feed or carriage
    return (WRITE ... ADVANCING PAGE, 0 LINES, or a Java's CRLF) stays in the record and is compared, and the final newline
    is compared too (diff.compare). read_records stays lenient for files we read as input."""
    if fmt == "fixed" or not path.exists():
        return read_records(path, fmt, length)
    lines = OutputLines(path.read_bytes().decode("latin-1").split("\n"))
    lines.final_newline = not lines[-1]
    if lines.final_newline:
        lines.pop()
    return lines


def write_records(path: Path, records: list[str], fmt: str = "line") -> None:
    path.write_bytes(("".join(records) if fmt == "fixed" else "".join(r + "\n" for r in records)).encode("latin-1"))


def _run_program(cmd: list[str], dd: dict[str, str], input_path: Path, workdir: Path, label: str,
                 out_format: tuple[str, int] = ("line", 0), extra_env: dict[str, str] | None = None,
                 timeout: int = 120) -> Run:
    output_path = workdir / f"{label}.out"
    env = {**CLOCK_ENV, **(extra_env or {}), f"DD_{dd['input']}": str(input_path), f"DD_{dd['output']}": str(output_path)}
    proc = _exec_side(side_of(label), cmd, env=env, cwd=workdir, timeout=timeout)
    return Run(True, proc.returncode, proc.stdout, proc.stderr, read_output(output_path, *out_format))


def _stand_ins(source: Path, modules: list[Path] | None, workdir: Path) -> list[str]:
    """Diocle's stated stand-ins (standin.py) for runtime routines the program calls but no source defines."""
    from .standin import stand_in_sources

    return [str(p) for p in stand_in_sources([source, *(modules or [])], workdir)]


def run_cobol(source: Path, copybook_dir: Path, dd: dict[str, str], input_path: Path, workdir: Path,
              out_format: tuple[str, int] = ("line", 0), modules: list[Path] | None = None,
              collation: str = "ascii") -> Run:
    """modules: CALLed programs, linked into the same executable (the first source is the entry point).
    collation "ebcdic" compares and sorts alphanumeric data in mainframe (EBCDIC) order."""
    exe = workdir / "original"
    colseq = ["-fdefault-colseq=EBCDIC"] if collation == "ebcdic" else []
    build = build_executable(exe, source, [*(modules or []), *map(Path, _stand_ins(source, modules, workdir))],
                             [*IBM_FLAGS, *colseq, "-I", str(copybook_dir)], workdir)
    if build.returncode != 0:
        return Run(False, build.returncode, build.stdout, build.stderr)
    return _run_program([str(exe)], dd, input_path, workdir, "original", out_format)


def run_java(src_dir: Path, main_class: str, dd: dict[str, str], input_path: Path, workdir: Path,
             out_format: tuple[str, int] = ("line", 0), collation: str = "ascii") -> Run:
    classes = workdir / "classes"
    classes.mkdir(exist_ok=True)
    sources = sorted(str(p) for p in src_dir.rglob("*.java"))
    build = _exec(["javac", "-proc:none", "-d", str(classes), *sources])
    if build.returncode != 0:
        return Run(False, build.returncode, build.stdout, build.stderr)
    return _run_program(["java", "-cp", str(classes), main_class], dd, input_path, workdir, "converted", out_format,
                        {"DIOCLE_COLLATION": collation.upper()})


def build_cobol(source: Path, copybook_dir: Path, workdir: Path, modules: list[Path] | None = None,
                collation: str = "ascii", timeout: int = 120) -> tuple[list[str] | None, Run | None]:
    """Compile once; returns (command to run, None) or (None, failed Run)."""
    exe = workdir / "original"
    colseq = ["-fdefault-colseq=EBCDIC"] if collation == "ebcdic" else []
    build = build_executable(exe, source, [*(modules or []), *map(Path, _stand_ins(source, modules, workdir))],
                             [*IBM_FLAGS, *colseq, "-I", str(copybook_dir)], workdir, timeout=timeout)
    if build.returncode != 0:
        return None, Run(False, build.returncode, build.stdout, build.stderr)
    return [str(exe)], None


def build_java(src_dir: Path, main_class: str, workdir: Path) -> tuple[list[str] | None, Run | None]:
    classes = workdir / "classes"
    classes.mkdir(exist_ok=True)
    build = _exec(["javac", "-proc:none", "-d", str(classes), *sorted(str(p) for p in src_dir.rglob("*.java"))])
    if build.returncode != 0:
        return None, Run(False, build.returncode, build.stdout, build.stderr)
    return ["java", "-cp", str(classes), main_class], None


FAIL_CLOSED = ("the original was not built or run, which says nothing about whether it compiles; verification fails closed "
               "because of what the converted Java did: ")


def not_run(tamper: list[str]) -> Run:
    """The original's Run when the converted program tampered: compiled is None (not attempted), never False, which
    would read as "the original COBOL does not compile" and stop a run for a fault that is the Java's."""
    return Run(None, None, "", FAIL_CLOSED + "; ".join(tamper))


def original_sources(sample_dir: Path, meta: dict) -> list[Path]:
    """Everything the original is built from: its source, CALLed modules and every file under the copybook dir."""
    return ([sample_dir / meta["source"]] + [sample_dir / m for m in meta.get("modules", [])]
            + sorted(p for p in (sample_dir / meta["copybookDir"]).rglob("*") if p.is_file()))


def _sha(p: Path) -> str:
    import hashlib

    return hashlib.sha256(p.read_bytes()).hexdigest()


def attribute_timeout(timed_out: ProgramTimeout, tamper: list[str], run_original: Callable[[], object]) -> NoReturn:
    """The converted program ran past the limit, so the original has not run yet. Run it under the same limit before
    blaming the Java: a faithful Java of a program that never ends also never ends, and run_original raising its own
    ProgramTimeout reports that as the original's. A Java that also tampered gets the blame without it: the original
    must not run on what the Java touched."""
    if not tamper:
        run_original()
    raise timed_out


def guard_before(guarded: list[Path], work: Path) -> tuple[dict[str, str], set[str]]:
    """Taken just before the converted program runs, while the original has not run (its answer does not exist yet):
    hashes of the files the original will read or be built from, and the names already in its working directory."""
    return {str(p): _sha(p) for p in guarded if p.is_file()}, {p.name for p in work.iterdir()}


def guard_after(snapshot: tuple[dict[str, str], set[str]], work: Path) -> list[str]:
    """Why the original must not run (empty if nothing was touched): the converted program, running as the same user,
    changed a file the original reads or put a file where the original will run and write its output."""
    before, names = snapshot
    problems = [f"the converted program changed {Path(p).name}" for p, h in before.items()
                if not Path(p).is_file() or _sha(Path(p)) != h]
    problems += [f"the converted program created {p.name}" for p in sorted(work.iterdir()) if p.name not in names]
    return problems


def run_files(cmd: list[str], inputs: dict[str, Path], outputs: dict[str, tuple[str, int]], workdir: Path, label: str,
              extra_env: dict[str, str] | None = None, seeds: dict[str, Path] | None = None,
              timeout: int = 120) -> Run:
    """Run with every DD bound: inputs DD -> file, outputs DD -> (format, record length). Outputs land per DD.
    seeds: files opened I-O. Each run gets its own copy of the seed at the DD's path (the program updates it in
    place), and the file's final contents are read back like an output."""
    paths = {dd: workdir / f"{label}-{dd}.out" for dd in outputs}
    for dd, seed in (seeds or {}).items():
        paths[dd].write_bytes(seed.read_bytes())
    env = {**CLOCK_ENV, **(extra_env or {}), **{f"DD_{dd}": str(p) for dd, p in inputs.items()},
           **{f"DD_{dd}": str(p) for dd, p in paths.items()}}
    proc = _exec_side(side_of(label), cmd, env=env, cwd=workdir, timeout=timeout)
    files = {dd: read_output(paths[dd], *outputs[dd]) for dd in outputs}
    return Run(True, proc.returncode, proc.stdout, proc.stderr, output_files=files)
