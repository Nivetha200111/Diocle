"""Fixed-format COBOL parsing for the subset Diocle converts: copybook layouts and a program's file wiring.

Deterministic and dependency-free. Unsupported features are reported, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PIC = re.compile(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(\S+)")
_SIGN_LEADING_SEPARATE = re.compile(r"\bSIGN\s+(?:IS\s+)?LEADING\s+SEPARATE\b")
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


def apply_replacing(text: str, pairs: list[tuple[str, str]]) -> str:
    """COPY ... REPLACING: ==pseudo-text== pairs replace text, plain operands replace whole words."""
    for old, new in pairs:
        if old.startswith("=="):
            text = text.replace(old.strip("=").strip(), new.strip("=").strip())
        else:
            text = re.sub(rf"(?<![A-Z0-9-]){re.escape(old)}(?![A-Z0-9-])", new, text)
    return text


_REPLACING = re.compile(r"(==.*?==|[A-Z0-9:-]+)\s+BY\s+(==.*?==|[A-Z0-9:-]+)")


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


_USAGES = [(re.compile(r"\bCOMP(?:UTATIONAL)?-3\b|\bPACKED-DECIMAL\b"), "packed"),
           (re.compile(r"\bCOMP(?:UTATIONAL)?-5\b"), "binary-native"),
           (re.compile(r"\bCOMP(?:UTATIONAL)?-1\b"), "float4"),
           (re.compile(r"\bCOMP(?:UTATIONAL)?-2\b"), "float8"),
           (re.compile(r"\bCOMP(?:UTATIONAL)?(?:-4)?\b(?!-)|\bBINARY\b"), "binary"),
           (re.compile(r"\bNATIONAL\b"), "national"),
           (re.compile(r"\bCOMP(?:UTATIONAL)?-(?:6|X|N)\b"), "unsupported")]
_SIGN = re.compile(r"\bSIGN\s+(?:IS\s+)?(LEADING|TRAILING)(\s+SEPARATE)?")
_OCCURS = re.compile(r"\bOCCURS\s+(\d+)(?:\s+TO\s+(\d+))?(?:\s+TIMES)?")
_REDEFINES = re.compile(r"\bREDEFINES\s+([A-Z0-9-]+)")


@dataclass
class _Node:
    level: int
    name: str
    rest: str
    children: list["_Node"] = field(default_factory=list)


def _usage(rest: str) -> str | None:
    for pattern, usage in _USAGES:
        if pattern.search(rest):
            return usage
    return None


def _numeric(name: str, pic: str, usage: str, sign: tuple[str, bool] | None) -> dict | str:
    m = re.fullmatch(r"(S?)(9*)(P*)(?:V(9*))?", pic)
    if not m:
        if re.fullmatch(r"S?P+V?9+|S?VP+9+", pic):
            return f"{name}: leading P scaling (PIC {pic}) is not supported yet"
        return f"{name}: PIC {pic} is not supported yet"
    signed, nines, trailing_p, decimals = m.group(1) == "S", m.group(2), m.group(3), m.group(4) or ""
    if trailing_p and decimals:
        return f"{name}: PIC {pic} is not supported yet"
    if not (nines or decimals):
        return f"{name}: PIC {pic} has no digits"
    result = {"name": name, "kind": "numeric", "digits": len(nines) + len(trailing_p),
              "scale": len(decimals) - len(trailing_p), "signed": signed}
    if usage != "display":
        result["usage"] = usage
    elif signed:
        position, separate = sign or ("TRAILING", False)
        result["sign"] = f"{position.lower()}-separate" if separate else position.lower()
    return result


def _elementary(node: _Node, usage: str, sign: tuple[str, bool] | None) -> dict | str:
    if usage in ("float4", "float8"):
        return {"name": node.name, "kind": "numeric", "digits": 7, "scale": 2, "signed": True,
                "usage": "float", "bytes": 4 if usage == "float4" else 8}
    pic_match = _PIC.search(node.rest)
    if not pic_match:
        return f"{node.name}: no PIC clause"
    pic = _expand(pic_match.group(1))
    if usage == "national" or "N" in pic:
        return f"{node.name}: national (PIC N) data is not supported yet"
    if re.fullmatch(r"[XA]+", pic):
        return {"name": node.name, "kind": "alnum", "length": len(pic)}
    if re.search(r"[Z*,.B0/$+\-]|CR|DB", pic.lstrip("S")) and usage == "display":
        return {"name": node.name, "kind": "alnum", "length": len(pic.replace("V", "")), "edited": pic}
    return _numeric(node.name, pic, usage, sign)


def parse_copybook(text: str, *, code: bool = False) -> Layout:
    """Record layout of the 01 level in a copybook, or in already-extracted code (an FD's inline record) with code=True."""
    entries = [e.strip() for e in re.split(r"\.(?=\s|$)", text) if e.strip()] if code else _entries(text)
    roots: list[_Node] = []
    stack: list[_Node] = []
    for entry in entries:
        m = re.match(r"(\d{1,2})\s+([A-Z0-9][A-Z0-9-]*)\b(.*)", entry, re.S)
        if not m:
            continue
        level, name, rest = int(m.group(1)), m.group(2), m.group(3)
        if level == 88:
            if stack:
                stack[-1].children.append(_Node(88, name, rest))
            continue
        if level in (66, 77):
            continue
        node = _Node(level, name, rest)
        if level == 1:
            roots.append(node)
            stack = [node]
            continue
        while stack and stack[-1].level >= level:
            stack.pop()
        if not stack:
            continue
        stack[-1].children.append(node)
        stack.append(node)
    if not roots:
        return Layout("?", unsupported="no 01 level found")
    layout = Layout(roots[0].name)
    if len(roots) > 1:
        layout.unsupported = f"{len(roots)} record types (01 levels) share this file; variant records are not supported yet"
        return layout

    def walk(node: _Node, usage: str, sign, suffix: str, redefines: str | None) -> None:
        if layout.unsupported:
            return
        usage = _usage(node.rest) or usage  # USAGE on a group applies to everything under it
        sign_match = _SIGN.search(node.rest)
        if sign_match:
            sign = (sign_match.group(1), bool(sign_match.group(2)))
        redefined = _REDEFINES.search(node.rest)
        redefines = redefines or (redefined.group(1) if redefined else None)
        occurs = _OCCURS.search(node.rest)
        if re.search(r"\bSYNC(?:HRONIZED)?\b", node.rest):
            layout.unsupported = f"{node.name}: SYNCHRONIZED adds slack bytes that are not modelled yet"
            return
        if usage == "unsupported":
            layout.unsupported = f"{node.name}: this USAGE (COMP-6, COMP-X or COMP-N) is not supported"
            return
        if (occurs and occurs.group(2)) or re.search(r"\bDEPENDING\b", node.rest):
            layout.unsupported = f"{node.name}: OCCURS DEPENDING ON (variable-length record) is not supported yet"
            return
        repeats = [""] if not occurs else [f"({i})" for i in range(1, int(occurs.group(1)) + 1)]
        for rep in repeats:
            name_suffix = suffix + rep
            data_children = [c for c in node.children if c.level != 88]
            if data_children:
                for child in data_children:
                    walk(child, usage, sign, name_suffix, redefines)
                continue
            result = _elementary(node, usage, sign)
            if isinstance(result, str):
                layout.unsupported = result
                return
            result["name"] = node.name + name_suffix
            if redefines:
                result["redefines"] = redefines
            if result["kind"] == "alnum" and "edited" not in result:
                values = [v for c in node.children if c.level == 88 for v in _VALUES.findall(c.rest)]
                if values:
                    result["values"] = list(dict.fromkeys(values))
            layout.fields.append(result)

    for child in roots[0].children:
        if child.level != 88:
            walk(child, "display", None, "", None)
    if not layout.fields and not layout.unsupported:
        layout.unsupported = "no elementary fields found"
    return layout


@dataclass
class ProgramInfo:
    name: str
    copybooks: list[str]
    selects: dict[str, str]  # file name -> DD name
    fd_copybooks: dict[str, str | None]  # file name -> copybook member
    directions: dict[str, str]  # file name -> input | output
    calls: list[str]
    organizations: dict[str, str] = field(default_factory=dict)  # file name -> SEQUENTIAL | LINE SEQUENTIAL | INDEXED | ...
    replacing: dict[str, list[tuple[str, str]]] = field(default_factory=dict)  # FD file name -> COPY REPLACING pairs
    inline_records: dict[str, int] = field(default_factory=dict)  # FD file name -> 01 levels written inline
    exec_blocks: list[str] = field(default_factory=list)  # SQL, CICS, DLI
    fd_inline: dict[str, str] = field(default_factory=dict)  # FD file name -> its inline record entries (code)
    sort_files: set[str] = field(default_factory=set)  # SD (sort work) files: internal, not program I/O
    dynamic_calls: list[str] = field(default_factory=list)  # CALL identifier: the target is only known at run time
    resolved_calls: dict[str, str] = field(default_factory=dict)  # CALL identifier -> the one literal it can only hold
    stdout_display: bool = False  # the PROCEDURE DIVISION DISPLAYs something to stdout (not only UPON SYSERR)
    console_input: bool = False  # ACCEPT from the console/stdin: its input is not something the verifier can vary


def parse_program(text: str) -> ProgramInfo:
    code = " ".join(c.strip() for _, c in source_lines(text))
    name_match = re.search(r"\bPROGRAM-ID\.\s*([A-Z0-9][A-Z0-9-]*)", code)
    name = name_match.group(1) if name_match else "UNKNOWN"
    selects = dict(re.findall(r"\bSELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+(?:TO\s+)?'?([A-Z0-9-]+)'?", code))
    fd_copybooks: dict[str, str | None] = {}
    replacing: dict[str, list[tuple[str, str]]] = {}
    inline_records: dict[str, int] = {}
    fd_inline: dict[str, str] = {}
    for m in re.finditer(r"\bFD\s+([A-Z0-9-]+)(.*?)(?=\bFD\s|\bWORKING-STORAGE\b|\bLINKAGE\b|\bPROCEDURE\b|$)", code):
        copy = re.search(r"\bCOPY\s+([A-Z0-9-]+)(?:\s+REPLACING\s+(.*?)\.(?:\s|$))?", m.group(2))
        fd_copybooks[m.group(1)] = copy.group(1) if copy else None
        if copy and copy.group(2):
            replacing[m.group(1)] = _REPLACING.findall(copy.group(2))
        inline_records[m.group(1)] = len(re.findall(r"(?:^|\s)01\s+[A-Z0-9-]+", m.group(2)))
        start = re.search(r"(?:^|\s)(01\s+[A-Z0-9-]+.*)", m.group(2), re.S)
        if not copy and start:
            fd_inline[m.group(1)] = start.group(1)
    organizations = {}
    for m in re.finditer(r"\bSELECT\s+([A-Z0-9-]+)(.*?)(?=\bSELECT\s|\bDATA\s+DIVISION\b|$)", code):
        org = re.search(r"\bORGANIZATION\s+(?:IS\s+)?(LINE\s+SEQUENTIAL|RECORD\s+SEQUENTIAL|SEQUENTIAL|INDEXED|RELATIVE)", m.group(2))
        organizations[m.group(1)] = re.sub(r"\s+", " ", org.group(1)) if org else "SEQUENTIAL"
    exec_blocks = sorted(set(re.findall(r"\bEXEC\s+(SQL|CICS|DLI|SQLIMS)\b", code)))
    directions: dict[str, str] = {}
    tokens = re.findall(r"[A-Z0-9][A-Z0-9-]*|[^\sA-Z0-9]", code)
    modes: dict[str, set[str]] = {}
    for i, token in enumerate(tokens):
        if token != "OPEN":
            continue
        mode = None
        for word in tokens[i + 1 :]:  # the OPEN statement ends at the first word that is neither a mode nor a file
            if word in ("INPUT", "OUTPUT", "EXTEND", "I-O"):
                mode = word
            elif word in selects and mode:
                modes.setdefault(word, set()).add(mode)
                directions[word] = ("input" if mode == "INPUT" else "output" if mode in ("OUTPUT", "EXTEND")
                                    else "io")
            else:
                break
    for word, seen in modes.items():
        if "I-O" in seen and len(seen) > 1:  # opened I-O here and another way there: not a shape we can seed and compare
            directions[word] = "unknown"
    sort_files = set(re.findall(r"\bSD\s+([A-Z0-9-]+)", code))
    for m in re.finditer(r"\bSORT\s+[A-Z0-9-]+.*?(?=\bSORT\s|$)", code):  # SORT ... USING in-files GIVING out-files
        stmt = m.group(0)
        for phrase, direction in (("USING", "input"), ("GIVING", "output")):
            words = re.search(rf"\b{phrase}\s+((?:[A-Z0-9-]+\s*)+)", stmt)
            for word in (words.group(1).split() if words else []):
                if word in selects:
                    directions[word] = direction
                elif word not in sort_files:
                    break
    copybooks = list(dict.fromkeys(re.findall(r"\bCOPY\s+([A-Z0-9-]+)", code)))
    calls = list(dict.fromkeys(re.findall(r"\bCALL\s+['\"]([A-Z0-9-]+)['\"]", code)))
    dynamic_calls = sorted(set(re.findall(r"(?<![A-Z0-9-])CALL\s+([A-Z][A-Z0-9-]*)(?![A-Z0-9-])", code)))
    procedure = _tokens(code)
    procedure = procedure[_procedure_start(procedure):]
    resolved, still_dynamic = _resolve_dynamic_calls(code, procedure, dynamic_calls)
    calls = list(dict.fromkeys(calls + list(resolved.values())))
    stdout_display, console_input = _console_use(procedure)
    return ProgramInfo(name, copybooks, selects, fd_copybooks, directions, calls, organizations, replacing,
                       inline_records, exec_blocks, fd_inline, sort_files, still_dynamic, resolved,
                       stdout_display, console_input)


# --- CALL identifier: resolved statically only when nothing but literals can ever be in it -------------------

_TOKEN = re.compile(r"""'[^']*'|"[^"]*"|[A-Z0-9][A-Z0-9-]*|[^\sA-Z0-9]""")

# Every verb that starts a statement. The verb nearest before a use of an identifier says how it is used, so an
# incomplete list would misread a modifying statement as a harmless one: keep it complete.
_VERBS = {"ACCEPT", "ADD", "ALLOCATE", "ALTER", "CALL", "CANCEL", "CLOSE", "COMPUTE", "CONTINUE", "DELETE", "DISPLAY",
          "DIVIDE", "ENTRY", "EVALUATE", "EXIT", "FREE", "GENERATE", "GO", "GOBACK", "IF", "INITIALIZE", "INITIATE",
          "INSPECT", "INVOKE", "MERGE", "MOVE", "MULTIPLY", "NEXT", "OPEN", "PERFORM", "RAISE", "READ", "RELEASE",
          "RESUME", "RETURN", "REWRITE", "SEARCH", "SET", "SORT", "START", "STOP", "STRING", "SUBTRACT", "SUPPRESS",
          "TERMINATE", "TRANSFORM", "UNLOCK", "UNSTRING", "USE", "VALIDATE", "WRITE", "XML", "JSON", "EXEC"}
# Places a data item is only read: conditions and DISPLAY.
_READ_ONLY = {"DISPLAY", "IF", "EVALUATE", "WHEN", "UNTIL"}


def _tokens(code: str) -> list[str]:
    return _TOKEN.findall(code)


def _procedure_start(tokens: list[str]) -> int:
    for i in range(len(tokens) - 1):
        if tokens[i] == "PROCEDURE" and tokens[i + 1] == "DIVISION":
            return i
    return len(tokens)


def _literal(token: str) -> str | None:
    return token[1:-1].rstrip() if token[:1] in ("'", '"') and len(token) >= 2 else None


def _pic_width(body: str) -> int | None:
    """Characters in an alphanumeric PIC (X(8), XXXX); None for any other picture."""
    m = re.search(r"\bPIC(?:TURE)?\s+(?:IS\s+)?([A-Z0-9()]+)", body)
    if not m or not re.fullmatch(r"(?:X(?:\(\d+\))?)+", m.group(1)):
        return None
    return sum(int(r) if r else 1 for r in re.findall(r"X(?:\((\d+)\))?", m.group(1)))


def _definition(code: str, identifier: str) -> tuple[str | None, bool, int | None]:
    """(the literal in the item's VALUE clause or None, whether the item is a plain elementary WORKING-STORAGE
    item at level 01 or 77 that nothing redefines, renames, gives condition names to, or repeats, and its PIC X
    width). Copybooks are not expanded, so any COPY in WORKING-STORAGE (which could redefine it) keeps it dynamic."""
    start, end = code.find("WORKING-STORAGE SECTION"), code.find("PROCEDURE DIVISION")
    linkage = code.find("LINKAGE SECTION")
    if linkage != -1 and start != -1 and linkage > start:
        end = min(end, linkage) if end != -1 else linkage
    name = re.escape(identifier)
    entries = list(re.finditer(rf"(?<![A-Z0-9-])(\d{{1,2}})\s+{name}(?![A-Z0-9-])([^.]*)\.", code))
    if start == -1 or len(entries) != 1:
        return None, False, None
    m = entries[0]
    if not (start < m.start() and (end == -1 or m.start() < end)):
        return None, False, None  # FILE SECTION, LINKAGE or a copybook: its contents are set from outside
    body = m.group(2)
    elementary = (m.group(1) in ("01", "77") and re.search(r"\bPIC(?:TURE)?\b", body) is not None
                  and not re.search(r"\b(?:REDEFINES|OCCURS|RENAMES|EXTERNAL|GLOBAL|BASED)\b", body)
                  and not re.search(rf"\bREDEFINES\s+{name}(?![A-Z0-9-])", code)
                  and not re.search(rf"\bRENAMES\s+{name}(?![A-Z0-9-])", code)  # a level-66 alias can assign it
                  and not re.match(r"\s*88\s", code[m.end():])  # SET condition TO TRUE changes it unseen
                  and not re.search(r"\bCOPY\s", code[start : end if end != -1 else len(code)]))
    value = re.search(r"""\bVALUE\s+(?:IS\s+)?('[^']*'|"[^"]*")""", body)
    return (_literal(value.group(1)) if value else None), elementary, _pic_width(body)


def _assigned_values(procedure: list[str], identifier: str) -> list[str] | None:
    """The literals moved into the identifier, or None when anything else can change it or lets its value escape
    (STRING, UNSTRING, ACCEPT, READ INTO, INITIALIZE, SET, INSPECT, arithmetic, PERFORM VARYING, CALL ... USING it,
    a subscript or reference modification, a MOVE from anything but one quoted literal)."""
    values = []
    for i, token in enumerate(procedure):
        if token != identifier:
            continue
        if i + 1 < len(procedure) and procedure[i + 1] == "(":
            return None
        j = i - 1
        while j >= 0 and procedure[j] not in _VERBS and procedure[j] not in _READ_ONLY and procedure[j] != ".":
            j -= 1
        if j < 0 or procedure[j] == ".":
            return None
        verb = procedure[j]
        if verb == "CALL":
            if j != i - 1:
                return None  # passed as an argument or RETURNING target: the called program may change it
        elif verb == "MOVE":
            if "TO" not in procedure[j + 1 : i]:
                continue  # the source of a MOVE: only read
            source = procedure[j + 1 : procedure.index("TO", j + 1)]
            if len(source) != 1 or _literal(source[0]) is None:
                return None  # also covers MOVE CORRESPONDING and any non-literal source
            values.append(_literal(source[0]))
        elif verb not in _READ_ONLY:
            return None
    return values


def _resolve_dynamic_calls(code: str, procedure: list[str], dynamic_calls: list[str]) -> tuple[dict[str, str], list[str]]:
    """Split CALL identifier targets into ({identifier: the literal program name it can only hold}, still dynamic).

    Resolved only when the identifier is a plain WORKING-STORAGE item, every assignment to it anywhere in the
    PROCEDURE DIVISION is MOVE 'literal', and the VALUE clause and all those literals agree on one name. Anything
    else that could assign it keeps the call dynamic (refused): a wrong resolution would translate the wrong
    program, which is worse than a missed feature."""
    resolved, still_dynamic = {}, []
    for identifier in dynamic_calls:
        initial, plain, width = _definition(code, identifier)
        moves = _assigned_values(procedure, identifier) if plain else None
        names = set(([initial] if initial is not None else []) + (moves or []))
        # a literal longer than the item's PIC X(n) is truncated at run time, so the name would be wrong
        if (moves is None or len(names) != 1 or not re.fullmatch(r"[A-Z][A-Z0-9-]*", next(iter(names)))
                or width is None or len(next(iter(names))) > width):
            still_dynamic.append(identifier)
        else:
            resolved[identifier] = next(iter(names))
    return resolved, still_dynamic


def _console_use(procedure: list[str]) -> tuple[bool, bool]:
    """(some DISPLAY writes to stdout, some ACCEPT reads the console). DISPLAY ... UPON SYSERR goes to stderr."""
    stdout_display = console_input = False
    for i, token in enumerate(procedure):
        if token == "DISPLAY":
            j = i + 1
            while j < len(procedure) and procedure[j] not in _VERBS and procedure[j] != ".":
                j += 1
            stmt = procedure[i + 1 : j]
            upon = stmt.index("UPON") if "UPON" in stmt else -1
            if not (upon != -1 and stmt[upon + 1 : upon + 2] in (["SYSERR"], ["STDERR"], ["ERROR"])):
                stdout_display = True
        elif token == "ACCEPT":
            tail = procedure[i + 2 : i + 4]
            if not (tail[:1] == ["FROM"] and tail[1:2] and tail[1] in ("DATE", "TIME", "DAY", "DAY-OF-WEEK")):
                console_input = True
    return stdout_display, console_input
