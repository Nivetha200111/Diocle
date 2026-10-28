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


def _exec(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None, timeout: int = 120):
    return subprocess.run(
        cmd, env={**os.environ, **(env or {})}, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def _run_program(cmd: list[str], dd: dict[str, str], input_path: Path, workdir: Path, label: str) -> Run:
    output_path = workdir / f"{label}.out"
    env = {f"DD_{dd['input']}": str(input_path), f"DD_{dd['output']}": str(output_path)}
    proc = _exec(cmd, env=env, cwd=workdir)
    lines = output_path.read_text().splitlines() if output_path.exists() else []
    return Run(True, proc.returncode, proc.stdout, proc.stderr, lines)


def run_cobol(source: Path, copybook_dir: Path, dd: dict[str, str], input_path: Path, workdir: Path) -> Run:
    exe = workdir / "original"
    build = _exec(["cobc", "-x", "-std=ibm", "-I", str(copybook_dir), "-o", str(exe), str(source)])
    if build.returncode != 0:
        return Run(False, build.returncode, build.stdout, build.stderr)
    return _run_program([str(exe)], dd, input_path, workdir, "original")


def run_java(src_dir: Path, main_class: str, dd: dict[str, str], input_path: Path, workdir: Path) -> Run:
    classes = workdir / "classes"
    classes.mkdir(exist_ok=True)
    sources = sorted(str(p) for p in src_dir.rglob("*.java"))
    build = _exec(["javac", "-d", str(classes), *sources])
    if build.returncode != 0:
        return Run(False, build.returncode, build.stdout, build.stderr)
    return _run_program(["java", "-cp", str(classes), main_class], dd, input_path, workdir, "converted")
