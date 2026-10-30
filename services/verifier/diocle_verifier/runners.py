"""Build and run the original COBOL (GnuCOBOL) and the converted Java with the same DD-style file bindings."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Run:
    compiled: bool
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    output_lines: list[str] = field(default_factory=list)
    output_files: dict[str, list[str]] = field(default_factory=dict)  # DD name -> records (multi-file runs)


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


def write_records(path: Path, records: list[str], fmt: str = "line") -> None:
    path.write_bytes(("".join(records) if fmt == "fixed" else "".join(r + "\n" for r in records)).encode("latin-1"))


def _run_program(cmd: list[str], dd: dict[str, str], input_path: Path, workdir: Path, label: str,
                 out_format: tuple[str, int] = ("line", 0), extra_env: dict[str, str] | None = None,
                 timeout: int = 120) -> Run:
    output_path = workdir / f"{label}.out"
    env = {**CLOCK_ENV, **(extra_env or {}), f"DD_{dd['input']}": str(input_path), f"DD_{dd['output']}": str(output_path)}
    proc = _exec(cmd, env=env, cwd=workdir, timeout=timeout)
    return Run(True, proc.returncode, proc.stdout, proc.stderr, read_records(output_path, *out_format))


def run_cobol(source: Path, copybook_dir: Path, dd: dict[str, str], input_path: Path, workdir: Path,
              out_format: tuple[str, int] = ("line", 0), modules: list[Path] | None = None,
              collation: str = "ascii") -> Run:
    """modules: CALLed programs, linked into the same executable (the first source is the entry point).
    collation "ebcdic" compares and sorts alphanumeric data in mainframe (EBCDIC) order."""
    exe = workdir / "original"
    colseq = ["-fdefault-colseq=EBCDIC"] if collation == "ebcdic" else []
    build = _exec(["cobc", "-x", "-std=ibm", *IBM_FLAGS, *colseq, "-I", str(copybook_dir), "-o", str(exe), str(source),
                   *(str(m) for m in modules or [])])
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
    build = _exec(["cobc", "-x", "-std=ibm", *IBM_FLAGS, *colseq, "-I", str(copybook_dir), "-o", str(exe), str(source),
                   *(str(m) for m in modules or [])], timeout=timeout)
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
    proc = _exec(cmd, env=env, cwd=workdir, timeout=timeout)
    files = {dd: read_records(paths[dd], *outputs[dd]) for dd in outputs}
    return Run(True, proc.returncode, proc.stdout, proc.stderr, output_files=files)
