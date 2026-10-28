"""Fixed-format COBOL parsing for the subset Diocle converts: copybook layouts and a program's file wiring.

Deterministic and dependency-free. Unsupported features are reported, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PIC = re.compile(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(\S+)")
_SIGN_LEADING_SEPARATE = re.compile(r"\bSIGN\s+(?:IS\s+)?LEADING\s+SEPARATE\b")
_BINARY = re.compile(r"\b(?:COMP(?:UTATIONAL)?(?:-\d)?|BINARY|PACKED-DECIMAL)\b")
_UNSUPPORTED = re.compile(r"\b(REDEFINES|OCCURS|SYNC(?:HRONIZED)?|JUST(?:IFIED)?)\b")
_VALUES = re.compile(r"'([^']*)'")


def source_lines(text: str) -> list[tuple[int, str]]:
    """(line number, code area columns 8-72) for each non-comment line of fixed-format source."""
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > 6 and line[6] in "*/":
            continue
        code = line[7:72].rstrip()
        if code.strip():
            out.append((number, code))
    return out


def _entries(text: str) -> list[str]:
    """Data description entries: code joined across lines, split on periods that end an entry."""
    joined = " ".join(code.strip() for _, code in source_lines(text))
    return [e.strip() for e in re.split(r"\.(?=\s|$)", joined) if e.strip()]


def _expand(pic: str) -> str:
    return re.sub(r"(.)\((\d+)\)", lambda m: m.group(1) * int(m.group(2)), pic.upper())


@dataclass
class Layout:
    record: str
    fields: list[dict] = field(default_factory=list)
    unsupported: str | None = None

    def as_dict(self) -> dict | None:
        if self.unsupported:
            return None
        return {"record": self.record, "fields": self.fields}


def parse_copybook(text: str) -> Layout:
    """Record layout of the first 01 level in a copybook (display fields only)."""
    layout: Layout | None = None
    last_field: dict | None = None
    for entry in _entries(text):
        m = re.match(r"(\d{1,2})\s+([A-Z0-9][A-Z0-9-]*)\b(.*)", entry, re.S)
        if not m:
            continue
        level, name, rest = int(m.group(1)), m.group(2), m.group(3)
        if level == 1:
            if layout:
                break  # one record per copybook
            layout = Layout(name)
            continue
        if layout is None:
            continue
        if level == 88:
            if last_field is not None and last_field["kind"] == "alnum":
                values = _VALUES.findall(rest)
                last_field.setdefault("values", [])
                last_field["values"] += [v for v in values if v not in last_field["values"]]
            continue
        unsupported = _UNSUPPORTED.search(rest)
        if unsupported:
            layout.unsupported = f"{name}: {unsupported.group(1)} is not supported yet"
            continue
        pic = _PIC.search(rest)
        if not pic:
            last_field = None  # group item
            continue
        if _BINARY.search(rest):
            layout.unsupported = f"{name}: binary or packed USAGE in a record is not supported yet"
            continue
        last_field = _field(name, _expand(pic.group(1)), bool(_SIGN_LEADING_SEPARATE.search(rest)))
        if last_field is None:
            layout.unsupported = f"{name}: PIC {pic.group(1)} is not supported yet"
            continue
        layout.fields.append(last_field)
    if layout is None:
        return Layout("?", unsupported="no 01 level found")
    if not layout.fields and not layout.unsupported:
        layout.unsupported = "no elementary fields found"
    return layout


def _field(name: str, pic: str, leading_separate: bool) -> dict | None:
    if re.fullmatch(r"X+", pic):
        return {"name": name, "kind": "alnum", "length": len(pic)}
    m = re.fullmatch(r"(S?)(9*)(?:V(9*))?", pic)
    if not m or not (m.group(2) or m.group(3)):
        return None
    signed = m.group(1) == "S"
    if signed and not leading_separate:
        return None  # trailing overpunch signs are not modelled yet
    result = {"name": name, "kind": "numeric", "digits": len(m.group(2)), "scale": len(m.group(3) or ""), "signed": signed}
    if signed:
        result["sign"] = "leading-separate"
    return result


@dataclass
class ProgramInfo:
    name: str
    copybooks: list[str]
    selects: dict[str, str]  # file name -> DD name
    fd_copybooks: dict[str, str | None]  # file name -> copybook member
    directions: dict[str, str]  # file name -> input | output
    calls: list[str]


def parse_program(text: str) -> ProgramInfo:
    code = " ".join(c.strip() for _, c in source_lines(text))
    name_match = re.search(r"\bPROGRAM-ID\.\s*([A-Z0-9][A-Z0-9-]*)", code)
    name = name_match.group(1) if name_match else "UNKNOWN"
    selects = dict(re.findall(r"\bSELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+(?:TO\s+)?'?([A-Z0-9-]+)'?", code))
    fd_copybooks: dict[str, str | None] = {}
    for m in re.finditer(r"\bFD\s+([A-Z0-9-]+)(.*?)(?=\bFD\s|\bWORKING-STORAGE\b|\bLINKAGE\b|\bPROCEDURE\b|$)", code):
        copy = re.search(r"\bCOPY\s+([A-Z0-9-]+)", m.group(2))
        fd_copybooks[m.group(1)] = copy.group(1) if copy else None
    directions: dict[str, str] = {}
    for m in re.finditer(r"\bOPEN\s+((?:(?:INPUT|OUTPUT|EXTEND|I-O)\s+(?:[A-Z0-9-]+\s*)+)+)", code):
        mode = None
        for token in m.group(1).split():
            if token in ("INPUT", "OUTPUT", "EXTEND", "I-O"):
                mode = token
            elif token in selects and mode:
                directions[token] = "input" if mode == "INPUT" else "output" if mode in ("OUTPUT", "EXTEND") else "unknown"
    copybooks = list(dict.fromkeys(re.findall(r"\bCOPY\s+([A-Z0-9-]+)", code)))
    calls = list(dict.fromkeys(re.findall(r"\bCALL\s+'([A-Z0-9-]+)'", code)))
    return ProgramInfo(name, copybooks, selects, fd_copybooks, directions, calls)
