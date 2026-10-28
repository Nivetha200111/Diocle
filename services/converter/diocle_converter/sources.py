"""Read a sample's COBOL program, copybooks and DD names (the converter's view of the input)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Program:
    sample_dir: Path
    name: str
    cobol: str
    copybooks: dict[str, str]
    dd: dict[str, str]

    @classmethod
    def load(cls, sample_dir: Path) -> "Program":
        sample_dir = sample_dir.resolve()
        meta = json.loads((sample_dir / "sample.json").read_text())
        copybook_dir = sample_dir / meta["copybookDir"]
        copybooks = {p.name: p.read_text() for p in sorted(copybook_dir.glob("*.cpy"))}
        return cls(sample_dir, meta["program"], (sample_dir / meta["source"]).read_text(), copybooks, meta["dd"])

    def as_text(self) -> str:
        parts = [f"=== {self.name}.cbl ===\n{self.cobol}"]
        parts += [f"=== {name} ===\n{text}" for name, text in self.copybooks.items()]
        return "\n".join(parts)
