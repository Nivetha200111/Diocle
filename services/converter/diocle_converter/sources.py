"""Read a sample's COBOL program, copybooks and DD names (the converter's view of the input)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from diocle_verifier.runners import _FREE_DIRECTIVE


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
    ksds: dict | None = None  # sample.json `ksds` (subset, keyLinks): the program uses keyed (INDEXED) files in the verified subset
    keyed: list[dict] = field(default_factory=list)  # [{dd, direction, keyed, recordLength}] for those files
    stand_ins: tuple[str, ...] = ()  # runtime routines verified against Diocle's stated stand-in (CEE3ABD)

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
            files = [{"dd": f["dd"], "direction": f["direction"], **({"keyed": f["keyed"]} if f.get("keyed") else {})}
                     for f in meta["files"]]
        else:
            files = [{"dd": meta["dd"]["input"], "direction": "input"}, {"dd": meta["dd"]["output"], "direction": "output"}]
        dd = meta.get("dd") or {"input": "", "output": ""}
        keyed = []
        if not anyway and meta.get("ksds"):
            from diocle_verifier.layout import load_fields, record_length  # the record length as the verifier computes it

            keyed = [{"dd": f["dd"], "direction": f["direction"], "keyed": f["keyed"],
                      "recordLength": record_length(load_fields(f["layout"]))} for f in meta["files"] if f.get("keyed")]
        stand_ins: tuple[str, ...] = ()
        if not anyway:  # the same detection the verifier links the stand-ins by, so prompt and build always agree
            from diocle_verifier.standin import stand_ins_for

            stand_ins = tuple(stand_ins_for([sample_dir / meta["source"], *(sample_dir / m for m in meta.get("modules", []))]))
        return cls(sample_dir, meta["program"], (sample_dir / meta["source"]).read_text(), copybooks, dd,
                   meta["javaConversion"]["mainClass"], modules, files, anyway, None if anyway else meta.get("sql"),
                   None if anyway else meta.get("ksds"), keyed, stand_ins)

    def io_text(self) -> str:
        if self.anyway:
            return ("Files: for each sequential file the COBOL names, read it from or write it to the path in environment "
                    "variable DD_<ddname>, as the program's SELECT ... ASSIGN names it. This program is NOT differential-tested.")
        plain = [f for f in self.files if not f.get("keyed")]
        reads = ", ".join(f"DD_{f['dd']}" for f in plain if f["direction"] == "input") or "none"
        writes = ", ".join(f"DD_{f['dd']}" for f in plain if f["direction"] == "output")
        updates = ", ".join(f"DD_{f['dd']}" for f in plain if f["direction"] == "io")
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
        for k in self.keyed:
            text += (f" {k['dd']} is a KEYED (INDEXED) file, opened {k['keyed'].get('openMode', '?')}, {k['recordLength']}-byte records, "
                     f"RECORD KEY {k['keyed']['recordKey']['field']} at byte offset {k['keyed']['recordKey']['offset']} length "
                     f"{k['keyed']['recordKey']['length']}, ACCESS {k['keyed']['accessMode']}: do NOT read or write it as a plain "
                     "file; reach it only through DioKsds (see the keyed-file contract). Its final contents are compared.")
        if not writes and not updates and not self.sql and not self.keyed:
            text += (" The program writes no file: what it DISPLAYs to stdout and its RETURN-CODE (the process exit "
                     "code) are the whole result and are compared byte for byte, so print exactly what each DISPLAY "
                     "prints (including numeric edited items and the newline) and nothing else on stdout.")
        return text

    def stand_in_text(self) -> str:
        """What the Java must do where the COBOL CALLs a routine the verifier replaces with a stated stand-in."""
        from .prompts import TRANSLATOR_CEE3ABD

        return TRANSLATOR_CEE3ABD if "CEE3ABD" in self.stand_ins else ""

    def uses_advancing(self) -> bool:
        """A WRITE with AFTER or BEFORE [ADVANCING] anywhere in what the model is given. Never on the convert-anyway prompt's
        path, which nothing compares. DISPLAY ... WITH NO ADVANCING does not count: it does not write a file."""
        return not self.anyway and any(_writes_advancing(text) for text in (self.cobol, *self.modules.values(), *self.copybooks.values()))

    def advancing_text(self, text: str) -> str:
        """text if the program writes with AFTER/BEFORE ADVANCING, otherwise nothing: every other program's prompt is unchanged."""
        return text if self.uses_advancing() else ""

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
        if self.ksds and not self.sql:
            from diocle_verifier.ksds import SUPPORT as KSDS_SUPPORT

            return ("=== DioKsds.java (the verifier's support class, provided; do not rewrite it) ===\n"
                    + (KSDS_SUPPORT / "DioKsds.java").read_text())
        if not self.sql:
            return ""
        from diocle_verifier.sqlpre import SUPPORT

        return "=== DioSql.java (the verifier's support class, provided; do not rewrite it) ===\n" + (SUPPORT / "DioSql.java").read_text()


_LITERAL = re.compile(r"\"[^\"\n]*\"|'[^'\n]*'")
_NO_ADVANCING = re.compile(r"(?<![\w-])NO\s+ADVANCING(?![\w-])", re.I)  # DISPLAY ... WITH NO ADVANCING
_ADVANCING_WORD = re.compile(r"(?<![\w-])ADVANCING(?![\w-])", re.I)
_WRITE_ADVANCING = re.compile(  # the word ADVANCING is optional: WRITE R AFTER 2 LINES
    r"(?<![\w-])WRITE\s+[\w-]+"  # the record
    r"(?:\s+FROM\s+(?:''|[\w-]+)(?:\s+(?:OF|IN)\s+[\w-]+)*(?:\s*\([^)]*\))*)?"  # FROM an item, qualified or subscripted, or a literal
    r"\s+(?:AFTER|BEFORE)(?![\w-])", re.I)


def _writes_advancing(source: str) -> bool:
    """Comments, literals and (in fixed format) the columns past 72 are not code, so they cannot turn the rule on."""
    lines = source.splitlines()
    free = bool(_FREE_DIRECTIVE.match(next((line for line in lines if line.strip()), "")))
    code = "\n".join((line if free else line[:72]).split("*>")[0] for line in lines if free or line[6:7] not in ("*", "/"))
    code = _NO_ADVANCING.sub("", _LITERAL.sub("''", code))
    return bool(_WRITE_ADVANCING.search(code) or _ADVANCING_WORD.search(code))


def _table_line(t: dict) -> str:
    cols = []
    for c in t["columns"]:
        kind = (f"{c['type']}({c['length']})" if c["type"] in ("CHAR", "VARCHAR")
                else f"DECIMAL({c['precision']},{c['scale']}) (stored x 10^{c['scale']})" if c["type"] == "DECIMAL" else c["type"])
        cols.append(f"{c['name']} {kind}{'' if c['nullable'] else ' NOT NULL'}")
    pk = f" PRIMARY KEY ({', '.join(t['primaryKey'])})" if t.get("primaryKey") else ""
    return f"TABLE {t['name']}: " + ", ".join(cols) + pk
