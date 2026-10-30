"""Precompiler for the verified EXEC SQL subset: rewrites a COBOL program so GnuCOBOL can run it against SQLite.

Every EXEC SQL statement becomes COBOL that moves host variables into work items (so COBOL itself does the
PIC/COMP-3/sign conversions, exactly as it would for any MOVE), one `CALL "DIOSQL"` into the C shim
(dbsupport/dioshim.c), and moves of the results back. The statement table (SQL text, kinds, argument specs) is a
generated C file compiled in with the shim. The parse is the analyzer's (diocle_analyzer.sqlsubset), so a statement the
analyzer accepted is exactly a statement that is rewritten here; anything else raises PrecompileError.

This is NOT IBM's precompiler and the engine is SQLite: see the README for what that does and does not prove.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from diocle_analyzer.sqlsubset import (Stmt, Table, _Ctx, expand_copies, expand_includes, find_blocks, host_defs,
                                       parse_statement, tokenize)

SUPPORT = Path(__file__).resolve().parent / "dbsupport"
KINDS = {"select-into": 1, "insert": 2, "update": 2, "delete": 2, "open": 3, "fetch": 4, "close": 5, "commit": 6, "rollback": 7}

SQLCA = """\
       01  SQLCA.
           05  SQLCAID             PIC X(8) VALUE 'SQLCA   '.
           05  SQLCABC             PIC S9(9) COMP-5 VALUE 136.
           05  SQLCODE             PIC S9(9) COMP-5 VALUE 0.
           05  SQLERRM.
               49  SQLERRML        PIC S9(4) COMP-5 VALUE 0.
               49  SQLERRMC        PIC X(70) VALUE SPACES.
           05  SQLERRP             PIC X(8) VALUE SPACES.
           05  SQLERRD             PIC S9(9) COMP-5 OCCURS 6 VALUE 0.
           05  SQLWARN             PIC X(8) VALUE SPACES.
           05  SQLSTATE            PIC X(5) VALUE '00000'."""


class PrecompileError(ValueError):
    pass


@dataclass
class Precompiled:
    cobol: str
    stmt_c: str
    statements: list[Stmt]


def _c(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _members(copybook_dir: Path | None) -> dict[str, str]:
    if not copybook_dir or not copybook_dir.is_dir():
        return {}
    return {p.stem.upper(): p.read_text(errors="replace") for p in copybook_dir.iterdir() if p.is_file()}


def _line(text: str) -> str:
    out = "           " + text
    if len(out) > 72:
        raise PrecompileError(f"generated line too long: {text}")
    return out


def _work_item(name: str, bind) -> list[str]:
    pic = f"X({bind.length})" if bind.kind == "X" else (
        f"S9({bind.length})V9({bind.scale})" if bind.scale else f"S9({bind.length})")
    sign = " SIGN IS LEADING SEPARATE" if bind.kind == "N" else ""
    return [f"       01  {name}.", f"           05  {name}-F PIC X.", f"           05  {name}-V PIC {pic}{sign}."]


def precompile(source: Path, copybook_dir: Path | None, tables: list[dict]) -> Precompiled:
    members = _members(copybook_dir)
    text = expand_includes(source.read_text(errors="replace"), members.get)
    lines = text.splitlines()
    ctx = _Ctx({t["name"]: Table.from_dict(t) for t in tables}, host_defs(expand_copies(text, members)))
    blocks = find_blocks(lines)
    proc_line = next((i for i, l in enumerate(lines) if re.search(r"\bPROCEDURE\s+DIVISION\b", l[7:72], re.I) and l[6:7] not in "*/"),
                     len(lines))
    parsed: list[Stmt] = []
    for b in blocks:
        s = parse_statement(b.text, b.line, ctx)
        if s.reason:
            raise PrecompileError(s.reason)
        parsed.append(s)
    cursor_no: dict[str, int] = {}
    for s in parsed:
        if s.cursor and s.cursor not in cursor_no:
            cursor_no[s.cursor] = len(cursor_no)
    if len(cursor_no) > 32:
        raise PrecompileError("more than 32 cursors")
    table_rows: list[tuple] = []  # (kind, cursor, sql, args) per emitted CALL, index = statement number
    work: list[str] = []
    out: list[str] = []
    cursor_pos = 0
    for b, s in zip(blocks, parsed):
        out += lines[cursor_pos:b.first]
        cursor_pos = b.last + 1
        if b.prefix.strip():
            out.append("           " + b.prefix.strip())
        gen: list[str]
        procedural = b.first > proc_line
        if s.kind == "include":
            out += SQLCA.splitlines()
            out.append("      *DIO-WORK-ITEMS")
            gen = []
            b.suffix = ""
        elif s.kind not in KINDS and not procedural:
            gen = [f"      * SQL {s.kind} removed by the Diocle precompiler (declaration)"]
            b.suffix = ""
        elif s.kind not in KINDS:
            gen = ["           CONTINUE"]
        else:
            n = len(table_rows)
            args = s.inputs + s.outputs
            names = [f"DIO-W{n}-{k + 1}" for k in range(len(args))]
            for name, bind in zip(names, args):
                work += _work_item(name, bind)
            gen = []
            for name, bind in zip(names, s.inputs):
                gen.append(_line(f"MOVE 'Y' TO {name}-F"))
                gen.append(_line(f"MOVE {bind.host} TO {name}-V"))
                if bind.indicator:
                    gen.append(_line(f"IF {bind.indicator} < 0 MOVE 'N' TO {name}-F END-IF"))
            call = [_line(f'CALL "DIOSQL" USING BY CONTENT "{n:04d}"'), _line("    BY REFERENCE SQLCA")]
            call += [_line(f"    BY REFERENCE {name}") for name in names]
            gen += call
            for name, bind in zip(names[len(s.inputs):], s.outputs):
                gen.append(_line(f"IF {name}-F = 'Y' MOVE {name}-V TO {bind.host} END-IF"))
                if bind.indicator:
                    gen.append(_line(f"IF {name}-F = 'Y' MOVE 0 TO {bind.indicator} END-IF"))
                    gen.append(_line(f"IF {name}-F = 'N' MOVE -1 TO {bind.indicator} END-IF"))
            specs = [x.spec() for x in s.inputs] + [x.spec(no_indicator=True) for x in s.outputs]
            table_rows.append((KINDS[s.kind], cursor_no.get(s.cursor or "", 0),
                               s.sql if s.kind in ("select-into", "insert", "update", "delete", "open") else "", ",".join(specs)))
        if gen and b.suffix.strip():
            if len(gen[-1]) + len(b.suffix.strip()) > 72:  # column 73 on is ignored by the compiler: never let a period fall off
                gen.append("           " + b.suffix.strip())
            else:
                gen[-1] += b.suffix.strip()
        out += gen
    out += lines[cursor_pos:]
    cobol = "\n".join(out) + "\n"
    if "      *DIO-WORK-ITEMS" not in cobol and any(s.kind in KINDS for s in parsed):
        raise PrecompileError("EXEC SQL INCLUDE SQLCA is required")
    cobol = cobol.replace("      *DIO-WORK-ITEMS", "\n".join(work) if work else "      * (no work items)")
    n = len(table_rows)
    c = ["/* generated by the Diocle precompiler (sqlpre.py); do not edit */",
         f"const int dio_nstmts = {n};",
         "const int dio_kind[] = {" + ", ".join(str(r[0]) for r in table_rows) + ", 0};",
         "const int dio_cursor[] = {" + ", ".join(str(r[1]) for r in table_rows) + ", 0};",
         "const char *dio_sql[] = {" + ", ".join(_c(r[2]) for r in table_rows) + ", 0};",
         "const char *dio_args[] = {" + ", ".join(_c(r[3]) for r in table_rows) + ", 0};"]
    return Precompiled(cobol, "\n".join(c) + "\n", parsed)
