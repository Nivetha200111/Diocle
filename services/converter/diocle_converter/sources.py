"""Read a sample's COBOL program, copybooks and DD names (the converter's view of the input)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Program:
    sample_dir: Path
    name: str
    cobol: str
    copybooks: dict[str, str]
    dd: dict[str, str]
    main_class: str  # the class name the verifier runs
    modules: dict[str, str] = field(default_factory=dict)  # CALLed programs: file name -> source

    @classmethod
    def load(cls, sample_dir: Path) -> "Program":
        sample_dir = sample_dir.resolve()
        meta = json.loads((sample_dir / "sample.json").read_text())
        copybook_dir = sample_dir / meta["copybookDir"]
        copybooks = {p.name: p.read_text() for p in sorted(copybook_dir.glob("*.cpy"))}
        modules = {Path(m).name: (sample_dir / m).read_text() for m in meta.get("modules", [])}
        return cls(sample_dir, meta["program"], (sample_dir / meta["source"]).read_text(), copybooks, meta["dd"],
                   meta["javaConversion"]["mainClass"], modules)

    def as_text(self) -> str:
        parts = [f"=== {self.name}.cbl ===\n{self.cobol}"]
        parts += [f"=== {name} (CALLed by {self.name}; translate it too) ===\n{text}" for name, text in self.modules.items()]
        parts += [f"=== {name} ===\n{text}" for name, text in self.copybooks.items()]
        return "\n".join(parts)
