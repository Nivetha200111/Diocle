"""The run's Java workspace: the only files the repair agent may read or change."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_copy(cls, source: Path, root: Path) -> "Workspace":
        root.mkdir(parents=True, exist_ok=True)
        for path in source.rglob("*.java"):
            target = root / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return cls(root)

    def _resolve(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if self.root not in path.parents or path.suffix != ".java":
            raise PermissionError(f"{relative!r} is outside the Java workspace or not a .java file")
        return path

    def list_files(self) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*.java"))

    def read(self, relative: str) -> str:
        return self._resolve(relative).read_text()

    def write(self, relative: str, content: str) -> None:
        path = self._resolve(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def patch(self, relative: str, old_text: str, new_text: str) -> str:
        path = self._resolve(relative)
        content = path.read_text()
        count = content.count(old_text)
        if not old_text or count != 1:
            return f"rejected: old_text must occur exactly once in {relative} (found {count})"
        start = content.index(old_text)
        updated = content.replace(old_text, new_text, 1)
        path.write_text(updated)
        first = updated.count("\n", 0, start)
        lines = updated.splitlines()
        last = first + new_text.count("\n")
        lo, hi = max(0, first - 2), min(len(lines), last + 3)
        excerpt = "\n".join(f"{n + 1:>4}| {lines[n]}" for n in range(lo, min(hi, lo + 40)))
        return f"applied. Lines {lo + 1}-{min(hi, lo + 40)} now read:\n{excerpt}"

    def compile(self) -> tuple[bool, str]:
        sources = [str(self.root / f) for f in self.list_files()]
        if not sources:
            return False, "no .java files in workspace"
        with tempfile.TemporaryDirectory() as out:
            proc = subprocess.run(["javac", "-d", out, *sources], capture_output=True, text=True, timeout=120)
        return proc.returncode == 0, (proc.stderr or proc.stdout).replace(str(self.root) + "/", "")[-4000:]
