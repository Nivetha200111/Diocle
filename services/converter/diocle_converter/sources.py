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
    files: list[dict] = field(default_factory=list)  # [{dd, direction}] for every file the program reads or writes
    anyway: dict | None = None  # convert-anyway sample: {"reason", "missingCopybooks"}; nothing here can be verified
    sql: dict | None = None  # sample.json `sql` (tables, subset): the program has EXEC SQL in the verified subset

    @classmethod
    def load(cls, sample_dir: Path) -> "Program":
        sample_dir = sample_dir.resolve()
        meta = json.loads((sample_dir / "sample.json").read_text())
        copybook_dir = sample_dir / meta["copybookDir"]
        copybooks = {p.name: p.read_text() for p in sorted(copybook_dir.glob("*.cpy"))}
        modules = {Path(m).name: (sample_dir / m).read_text() for m in meta.get("modules", [])}
        anyway = meta.get("convertAnyway")
        if anyway:
            files = []
        elif "files" in meta:
            files = [{"dd": f["dd"], "direction": f["direction"]} for f in meta["files"]]
        else:
            files = [{"dd": meta["dd"]["input"], "direction": "input"}, {"dd": meta["dd"]["output"], "direction": "output"}]
        dd = meta.get("dd") or {"input": "", "output": ""}
        return cls(sample_dir, meta["program"], (sample_dir / meta["source"]).read_text(), copybooks, dd,
                   meta["javaConversion"]["mainClass"], modules, files, anyway, None if anyway else meta.get("sql"))

    def io_text(self) -> str:
        if self.anyway:
            return ("Files: for each sequential file the COBOL names, read it from or write it to the path in environment "
                    "variable DD_<ddname>, as the program's SELECT ... ASSIGN names it. This program is NOT differential-tested.")
        reads = ", ".join(f"DD_{f['dd']}" for f in self.files if f["direction"] == "input") or "none"
        writes = ", ".join(f"DD_{f['dd']}" for f in self.files if f["direction"] == "output")
        updates = ", ".join(f"DD_{f['dd']}" for f in self.files if f["direction"] == "io")
        text = f"Input file paths come from environment variables {reads}"
        if writes:
            text += f"; write the outputs to {writes}"
        text += "."
        if updates:
            text += (f" {updates} names a file the COBOL opens I-O: it already holds records, so read it, apply what the "
                     "program REWRITEs, and write the result back to the same path. Records the program does not "
                     "REWRITE, and the record length, stay byte-identical. The final file contents are compared.")
        if self.sql:
            text += (" The program also uses EXEC SQL: the final contents of its tables are compared too (see the "
                     "embedded-SQL contract).")
        if not writes and not updates and not self.sql:
            text += (" The program writes no file: what it DISPLAYs to stdout and its RETURN-CODE (the process exit "
                     "code) are the whole result and are compared byte for byte, so print exactly what each DISPLAY "
                     "prints (including numeric edited items and the newline) and nothing else on stdout.")
        return text

    def as_text(self) -> str:
        parts = [f"=== {self.name}.cbl ===\n{self.cobol}"]
        parts += [f"=== {name} (CALLed by {self.name}; translate it too) ===\n{text}" for name, text in self.modules.items()]
        parts += [f"=== {name} ===\n{text}" for name, text in self.copybooks.items()]
        if self.sql:
            parts.append("=== DATABASE: tables the program uses (stand-in SQLite; DECIMAL and integers are stored as long x 10^scale) ===\n"
                         + "\n".join(_table_line(t) for t in self.sql["tables"]))
        return "\n".join(parts)

    def support_text(self) -> str:
        """The verifier's DioSql.java, shown to the translator and the repair agent (not part of the COBOL the guard reads)."""
        if not self.sql:
            return ""
        from diocle_verifier.sqlpre import SUPPORT

        return "=== DioSql.java (the verifier's support class, provided; do not rewrite it) ===\n" + (SUPPORT / "DioSql.java").read_text()


def _table_line(t: dict) -> str:
    cols = []
    for c in t["columns"]:
        kind = (f"{c['type']}({c['length']})" if c["type"] in ("CHAR", "VARCHAR")
                else f"DECIMAL({c['precision']},{c['scale']}) (stored x 10^{c['scale']})" if c["type"] == "DECIMAL" else c["type"])
        cols.append(f"{c['name']} {kind}{'' if c['nullable'] else ' NOT NULL'}")
    pk = f" PRIMARY KEY ({', '.join(t['primaryKey'])})" if t.get("primaryKey") else ""
    return f"TABLE {t['name']}: " + ", ".join(cols) + pk
